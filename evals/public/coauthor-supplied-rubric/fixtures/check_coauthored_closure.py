#!/usr/bin/env python3
"""Validate a closure built from a user-supplied rubric.

Four things beyond the ordinary closure checks:

0. ORDERING (the one that needs the trace): the policy read-back reached the
   user BEFORE the first materialization. A closure can be perfect on disk and
   still be the defect this scenario exists to catch — a scoring policy the
   agent invented, encoded and never showed anyone. Only the tool-call order
   distinguishes those two runs, so this check reads ``--trace``.
1. The supplied procedure landed as DATA. Every weight, threshold and verdict
   string the user gave is a row, not a literal in transform code.
2. The self-check (if the closure authored one) takes its expected values from
   landed data or the user's contract — never from the transform module or a
   copy of its constants.
3. The distribution read-back over derived classification columns runs, so a
   fabricated uniform gate is visible in the transcript.

Check 3 prints; it never fails the run. That mirrors the skill: it is a
read-back, not a gate.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
import sys
import tempfile
import types
from dataclasses import dataclass, field
from pathlib import Path


REQUIRED = (
    "spec.py",
    "models.py",
    "infra-profile.yaml",
    "transform/main.py",
    "requirements.txt",
    "CONTEXT.md",
    "csv-source-path",
)
FORBIDDEN = ("deployment-spec.yaml", "manifest.yaml", "models.yaml")

# The user's own values, from prompt.md. A closure that renames, reweights or
# re-bands any of these has edited the spec rather than encoded it.
SUPPLIED_WEIGHTS = {"40", "25", "20", "15"}
SUPPLIED_VERDICTS = {"ADVANCE", "HOLD", "REJECT", "NEEDS_MORE_INFO"}
# The prompt defines only the 5 and the 1 on every criterion, and gives no
# score->verdict bands. Both are agent-authored, so both must be proposed to
# the user before anything is written and landed as editable rows after.
CRITERIA = ("c1", "c2", "c3", "c4")


def fail(message: str) -> None:
    print(f"FAIL {message}")
    raise SystemExit(1)


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        fail(f"{label}: {detail}" if detail else label)
    print(f"PASS {label}")


def note(label: str, detail: str) -> None:
    """Report without gating. Used for the read-back."""
    print(f"NOTE {label}: {detail}")


@dataclass
class DuckDbOutput:
    path: str
    schema: str
    model_tables: dict
    models: dict = field(default_factory=dict)


def literal_strings_and_numbers(src: str) -> set[str]:
    """Every string and numeric literal in a module, as text."""
    out: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                out.add(node.value)
            elif isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                out.add(repr(node.value))
                out.add(str(node.value))
    return out


# --------------------------------------------------------------- ordering ---
# A write is any action that materializes part of the closure. Reading is not:
# the agent is explicitly allowed to read the source and its headers before the
# read-back, and must be, since the read-back describes that data.
#
# The markers MUST match what the backends actually emit:
# `_trace_from_stream` writes `[tool_use:Write] {json}`, never `Write(...)`.
# The older `Write(`/`Bash(` forms could not match any real trace, so
# `first_write_index` always returned None — and because a None short-circuits
# main() to "ALL CHECKS PASSED" below, every artifact check was skipped on every
# run. Keep this tuple in step with the emitter, not with how a trace reads.
# BOTH backends' emissions. This scenario is NOT ci_skip, and the PR gate runs
# codex — which has no Write/Edit tools at all: it materializes through
# `file_change` / `patch` / `apply_patch` items emitted under the same
# `[tool_use:<type>]` prefix. Listing only the Claude names left this gate blind
# on the exact backend CI uses.
WRITE_TOOLS = (
    "Write", "Edit", "MultiEdit", "NotebookEdit",     # ClaudeBackend
    "file_change", "patch", "apply_patch",            # CodexBackend
)
WRITE_MARKERS = tuple(f"[tool_use:{t}]" for t in WRITE_TOOLS)
BASH_MARKER = "[tool_use:Bash]"
# Shell is only a write when the command mutates. `head`/`cat`/`wc` on the
# supplied CSV is exactly the inspection the gate permits.
#
# Word-anchored and matched against the PARSED `command`: as bare substrings
# over the whole tool input, `dd ` matched inside `add `/`Add ` and the sibling
# `description` field could decide the gate. Interpreter names are deliberately
# absent — `python -c "import csv; print(...)"` is a read, and penalising it
# fails the agent that inspected carefully, inverting what the gate rewards.
SHELL_MUTATIONS = (
    r"\bmkdir\b", r"\bcp\s", r"\btouch\s", r"\btee\s", r">>",
    # `>` must target a path, not a number: `awk '{if ($5 > 3)}'` is a read.
    r">\s*[\"']?(?![0-9.]+(?:\s|\)|$)|\$\w+)[\w./~$]",
    r"(?<!pip )\binstall\s+-[mDdt]", r"\brsync\b", r"\bmv\s", r"\bsed\s+-i",
    r"\bdd\s",
)

# Evidence the policy read-back actually happened. Each family is a DISTINCT
# obligation from the skill's gate, so all four must appear — an agent that
# names the gap but proposes nothing has not given the user something to
# correct, and one that proposes without asking has not given them the turn.
READBACK_SIGNALS = {
    "names the incomplete scale": (
        r"\b(2\s*[-–/,]\s*3\s*[-–/,]\s*4|2,\s*3,?\s*(and\s+)?4"
        r"|intermediate|mid-?scale|mid-?point|only .{0,20}\b1\b.{0,20}\b5\b"
        r"|\b5\b.{0,15}and.{0,15}\b1\b.{0,40}(defined|given|anchor))"
    ),
    "proposes anchors": (
        r"\b(anchor|propose|proposed|proposal|suggest|I'd use|I would use)\b"
    ),
    "proposes verdict mapping": (
        r"(ADVANCE|HOLD|REJECT|NEEDS_MORE_INFO).{0,120}"
        r"(>=|≥|>|threshold|band|cut-?off|or above|or higher|\d\.\d)"
    ),
    "asks for correction or approval": (
        r"\b(correct|approve|confirm|adjust|change any|sound right|look right"
        r"|shall I|should I proceed|let me know|before I (build|create|write))\b"
    ),
}


def bash_command(line: str) -> str:
    """The `command` a Bash tool_use line ran, or "" if unrecoverable.

    Only the command is graded. The sibling `description` field is prose the
    agent writes ABOUT its intent, so letting it reach the mutation matchers
    lets a phrase like "Add up the criteria columns" decide a hard gate.
    """
    payload = line.split(BASH_MARKER, 1)[1].strip() if BASH_MARKER in line else ""
    try:
        obj = json.loads(payload)
        if isinstance(obj, dict):
            return str(obj.get("command", ""))
    except ValueError:
        pass
    # Truncated payload — the trace caps tool inputs, so this is the ordinary
    # case for a long command. Slice the command value out rather than falling
    # back to the whole payload, which would re-admit `description`.
    m = re.search(r'"command"\s*:\s*"((?:[^"\\]|\\.)*)', payload)
    if m:
        return m.group(1)
    # CodexBackend emits the RAW command after the marker, no JSON at all
    # (`[tool_use:Bash] mkdir -p ws/data`). Returning "" for that shape made
    # every shell mutation invisible on the backend the PR gate actually runs.
    # There is no `description` field here, so the payload IS the command.
    return "" if payload.startswith("{") else payload


def first_write_index(trace_lines: list[str]) -> int | None:
    """Index of the first line that materializes something. None if never."""
    for i, line in enumerate(trace_lines):
        if any(m in line for m in WRITE_MARKERS):
            return i
        if BASH_MARKER in line:
            cmd = bash_command(line)
            if any(re.search(p, cmd) for p in SHELL_MUTATIONS):
                return i
    return None


SKILL_LOAD = re.compile(r'"skill":\s*"[^"]*?:(nxd-[a-z0-9-]+)"')


def check_routing(trace: str) -> None:
    """The orchestrator must be reached for before the construction specialist.

    This grades SKILL SELECTION — the model's free choice among the attached
    skills, driven only by their descriptions. It is the step that decides
    whether the policy gate is even in scope, and it happens before any skill
    body executes, so nothing inside a skill can compensate for getting it
    wrong. An end-to-end "build me a data product" request has to reach
    nxd-pocket-loop, which gathers intent, source, questions and any supplied
    procedure; going straight to nxd-generate-dp is the observed failure.
    """
    loads = SKILL_LOAD.findall(trace)
    if not loads:
        # No skill at all is a different failure, already covered by the
        # read-back checks: nothing here to grade.
        note("routing", "no skill was loaded; read-back checks decide this run")
        return
    check(
        "routing:orchestrator-first",
        loads[0] != "nxd-generate-dp",
        f"first skill loaded was {loads[0]!r}; an end-to-end build request must "
        f"enter through nxd-pocket-loop, which gathers the inputs and runs the "
        f"policy read-back. Skill order was: {' -> '.join(loads)}",
    )


def check_ordering(trace: str) -> None:
    """Every read-back signal must appear before the first materialization."""
    lines = trace.split("\n")
    w = first_write_index(lines)
    # No write at all is a legitimate pass for this gate: the agent stopped and
    # asked, which is exactly the required behaviour. Later checks that need a
    # landed closure are skipped by main() in that case.
    before = "\n".join(lines[:w] if w is not None else lines)
    where = f"first write at trace line {w}" if w is not None else "no write occurred"

    for label, pattern in READBACK_SIGNALS.items():
        check(
            f"pre-build:{label}",
            re.search(pattern, before, re.IGNORECASE | re.DOTALL) is not None,
            f"no evidence before any materialization ({where}). The policy "
            f"read-back must precede the first Write/Edit/mkdir/copy, not "
            f"follow it.",
        )


def module_constants(src: str) -> dict[str, str]:
    """Module-level COMPOSITE constants, name -> structural dump.

    Composite only (dict/list/set/tuple with 2+ elements). A shared scalar like
    SCHEMA = "main" is coincidence; a shared weight table is a copy.
    """
    out: dict[str, str] = {}
    for node in ast.parse(src).body:
        if not isinstance(node, ast.Assign):
            continue
        v = node.value
        size = (
            len(v.keys) if isinstance(v, ast.Dict)
            else len(v.elts) if isinstance(v, (ast.List, ast.Set, ast.Tuple))
            else 0
        )
        if size < 2:
            continue
        for tgt in node.targets:
            if isinstance(tgt, ast.Name):
                out[tgt.id] = ast.dump(v)
    return out


def self_check_provenance(src: str, transform_src: str) -> list[str]:
    """Where the checker's expected values come from.

    Both halves matter. An import ban alone is satisfied by pasting the
    transform's constants into the checker — no import, identical tautology.
    """
    problems: list[str] = []
    tree = ast.parse(src)

    # Importing the transform to RUN it is what a dry-run does — that is the code
    # under test being invoked, not an expectation. What is forbidden is
    # importing its VALUES and then asserting against them. Allow the entry
    # points and the model lists; flag everything else.
    RUNNABLE = {"ingest", "BASE_MODELS", "PHYSICAL_MODELS", "DERIVED_MODELS", "main"}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] == "transform" or node.module == "main":
                values = [a.name for a in node.names if a.name not in RUNNABLE]
                if values:
                    problems.append(
                        f"imports {', '.join(values)} from the module under test "
                        f"({node.module})"
                    )

    # The copied-constants loophole: a module-level constant whose VALUE is
    # byte-identical to one in the transform is the same tautology as importing
    # it. Compare structurally so formatting differences do not hide it.
    t_consts = module_constants(transform_src)
    t_values = {v: k for k, v in t_consts.items()}
    for name, value in module_constants(src).items():
        if value in t_values:
            problems.append(
                f"re-declares {name} with the same value as the transform's "
                f"{t_values[value]} — a copy, not an independent expectation"
            )
    return problems


def main(root: Path, trace_path: Path | None = None) -> None:
    root = root.resolve()

    # ---- 0. ORDERING — read-back before any materialization -----------------
    # Runs first because it is the gate the others cannot see: checks 1-3 grade
    # the artifact, and a silently-invented policy produces a perfect artifact.
    if trace_path is not None and trace_path.is_file():
        trace = trace_path.read_text(errors="ignore")
        check_routing(trace)
        check_ordering(trace)
        if first_write_index(trace.split("\n")) is None:
            # Stopped and asked without writing: the gate's ideal outcome. There
            # is no closure to grade, and demanding one would punish exactly the
            # behaviour under test.
            print("NOTE agent stopped for approval before materializing — "
                  "no closure to grade, which satisfies this scenario's gate")
            print("ALL CHECKS PASSED")
            return

    for rel in REQUIRED:
        check(f"present:{rel}", (root / rel).is_file(), f"missing {rel}")
    for rel in FORBIDDEN:
        check(f"absent:{rel}", not (root / rel).exists(), f"supervisor-compiled {rel} authored by hand")

    # ---- supplied data preserved --------------------------------------------
    shipped = Path(__file__).parent / "data" / "applicants" / "applicants.csv"
    landed = root / "data" / "applicants" / "applicants.csv"
    check("csv-present", landed.is_file(), "data/applicants/applicants.csv missing")
    check(
        "csv-unmodified",
        hashlib.sha256(landed.read_bytes()).hexdigest()
        == hashlib.sha256(shipped.read_bytes()).hexdigest(),
        "the supplied export was edited",
    )

    transform_src = (root / "transform" / "main.py").read_text()
    models_src = (root / "models.py").read_text()

    # ---- 1. the supplied procedure landed as data ---------------------------
    # The rubric is parameterization. Its values belong in rows the user can
    # correct, not in code they cannot read.
    lits = literal_strings_and_numbers(transform_src)

    leaked_weights = SUPPLIED_WEIGHTS & lits
    check(
        "weights-not-hardcoded",
        not leaked_weights,
        f"supplied weight(s) {sorted(leaked_weights)} appear as literals in "
        f"transform/main.py; land them as rows and read them",
    )

    leaked_verdicts = SUPPLIED_VERDICTS & lits
    check(
        "verdicts-not-hardcoded",
        not leaked_verdicts,
        f"supplied verdict string(s) {sorted(leaked_verdicts)} appear as literals "
        f"in transform/main.py; land them as rows and read them",
    )

    # The values have to exist SOMEWHERE, or they were dropped rather than landed.
    data_text = "\n".join(
        p.read_text(errors="ignore") for p in (root / "data").rglob("*.csv")
    )
    for v in sorted(SUPPLIED_VERDICTS):
        check(
            f"verdict-landed:{v}",
            v in data_text,
            f"verdict {v!r} appears in no landed data file — it was dropped, "
            f"not encoded",
        )

    # ---- 2. agent-authored policy is landed, visible and attributed ---------
    # The prompt defines only 5 and 1 on every criterion and gives no verdict
    # bands, so the intermediate anchors and the thresholds are the AGENT's.
    # They must be inspectable rows, and the ledger must say they were not the
    # user's — a landed row the agent wrote and one the user wrote are
    # indistinguishable in the table, and only the ledger tells them apart.
    check(
        "anchors-landed-as-data",
        any(
            "2" in p.read_text(errors="ignore") and "4" in p.read_text(errors="ignore")
            for p in (root / "data").rglob("*.csv")
            if "anchor" in p.name.lower() or "scale" in p.name.lower()
            or "rubric" in p.name.lower()
        ),
        "the intermediate anchors the agent authored (2/3/4 on every criterion) "
        "are in no landed CSV — they must be editable rows, not buried in code",
    )
    check(
        "thresholds-landed-as-data",
        any(
            any(v in p.read_text(errors="ignore") for v in SUPPLIED_VERDICTS)
            for p in (root / "data").rglob("*.csv")
            if "threshold" in p.name.lower() or "verdict" in p.name.lower()
            or "band" in p.name.lower()
        ),
        "the score->verdict bands the agent authored are in no landed CSV; the "
        "user cannot correct a threshold that exists only in transform code",
    )

    ledger = root / "data" / "nxd_decisions" / "nxd_decisions.csv"
    check(
        "decisions-ledger-present",
        ledger.is_file(),
        "every agent-authored ruling (anchors, bands, exceptional-resume rule) "
        "is a decision; data/nxd_decisions/nxd_decisions.csv is missing",
    )
    ledger_text = ledger.read_text().lower() if ledger.is_file() else ""
    check(
        "gap-attributed",
        ("anchor" in ledger_text or "scale" in ledger_text
         or "intermediate" in ledger_text),
        "no nxd_decisions row records that the intermediate anchors were "
        "agent-authored rather than user-supplied",
    )
    # The prose above can say "agent-authored" anywhere in the row. Provenance
    # is the queryable form of the same claim, and this scenario is the exact
    # case it exists for: the user supplied the rubric, the agent filled the
    # intermediate anchors. Both classes must therefore appear.
    if ledger.is_file():
        with ledger.open(newline="") as fh:
            ledger_rows = list(csv.DictReader(fh))
    else:
        ledger_rows = []
    provs = {(r.get("provenance") or "").strip() for r in ledger_rows}
    has_prov = bool(ledger_rows) and "provenance" in ledger_rows[0]
    check(
        "provenance-column-present",
        has_prov,
        "nxd_decisions has no provenance column, so a reviewer cannot query "
        "which rulings the agent authored and which the user supplied",
    )
    # Gate the value check on the column existing. Without the column every row
    # reads as '', so this would fire a SECOND failure blaming an
    # out-of-vocabulary value — pointing at a value problem that does not exist
    # and burying the real diagnosis the check above already gave.
    check(
        "provenance-vocabulary-valid",
        not has_prov or provs <= {"user_confirmed", "agent_authored",
                                  "source_derived", "deferred"},
        f"nxd_decisions.provenance carries values outside the fixed vocabulary: "
        f"{sorted(provs - {'user_confirmed', 'agent_authored', 'source_derived', 'deferred'})}",
    )
    check(
        "agent-authored-ruling-classified",
        "agent_authored" in provs,
        "no nxd_decisions row is classified agent_authored, yet the "
        "agent authored the intermediate anchors — the ledger reads as if the "
        "user supplied every value",
    )
    check(
        "user-supplied-ruling-classified",
        "user_confirmed" in provs,
        "no nxd_decisions row is classified user_confirmed, yet the rubric "
        "criteria and weights came from the user",
    )

    # ---- 3. self-check provenance -------------------------------------------
    for cand in sorted(root.glob("self_check*.py")) + sorted(root.glob("check_*.py")):
        if cand.name == Path(__file__).name:
            continue
        problems = self_check_provenance(cand.read_text(), transform_src)
        check(
            f"self-check-provenance:{cand.name}",
            not problems,
            "; ".join(problems)
            + " — an expected value comes from landed data or the user's "
            "contract, never from the module under test",
        )

    # ---- 4. run the transform ------------------------------------------------
    # Registered as real submodules, not attributes: a closure may write either
    # `import nxd` or `from nxd.data_product import on_transform`, and only
    # sys.modules entries satisfy the second form.
    nxd = types.ModuleType("nxd")
    nxd.__path__ = []  # marks it a package
    core = types.ModuleType("nxd.core")
    core.__path__ = []
    ctx = types.ModuleType("nxd.core.context")
    ctx.DuckDbOutput = DuckDbOutput
    dp = types.ModuleType("nxd.data_product")
    dp.on_transform = lambda *a, **k: (lambda fn: fn)
    dp.main = lambda: None
    nxd.data_product, nxd.core, core.context = dp, core, ctx
    sys.modules.update(
        {
            "nxd": nxd,
            "nxd.core": core,
            "nxd.core.context": ctx,
            "nxd.data_product": dp,
        }
    )

    sys.path.insert(0, str(root))
    from transform.main import BASE_MODELS, PHYSICAL_MODELS, ingest  # noqa: E402

    run = Path(tempfile.mkdtemp())
    out = DuckDbOutput(
        path=str(run / "data.duckdb"),
        schema="main",
        model_tables={m: m for m in PHYSICAL_MODELS},
    )
    ingest(duckdb=out, secrets={"csv_source": str((root / "data").resolve())})
    check("transform-complete", (run / ".transform-complete").is_file())

    import duckdb  # noqa: E402

    con = duckdb.connect(out.path, read_only=True)

    # ---- 4. UNKNOWN is preserved, not collapsed into a failure --------------
    # G3 is UNKNOWN for all 10 by the user's own rule ("the form never asks").
    # Rendering it as FAIL would silently turn "we didn't ask" into "they said
    # no" and change who is reviewable.
    derived = sorted(set(PHYSICAL_MODELS) - set(BASE_MODELS))
    all_values: set[str] = set()
    for m in derived:
        for (c,) in con.execute(
            f"SELECT name FROM pragma_table_info('{m}') WHERE type = 'VARCHAR'"
        ).fetchall():
            if c.startswith("_dlt_"):
                continue
            all_values |= {
                str(v[0]).strip().upper()
                for v in con.execute(f'SELECT DISTINCT "{c}" FROM main.{m}').fetchall()
                if v[0] is not None
            }
    check(
        "unknown-not-collapsed-to-fail",
        any("UNKNOWN" in v or "NOT STATED" in v or "NOT_STATED" in v
            for v in all_values),
        "no landed column carries an UNKNOWN/not-stated value, yet the user's "
        "G3 rule makes availability unknown for every row — an unasked question "
        "must not be recorded as a failure",
    )

    # ---- 5. distribution read-back (prints, never gates) --------------------
    # A fabricated gate is uniform. This does not decide whether that is wrong —
    # it makes it visible. Deciding would be the judgement that makes it
    # unreliable.
    for m in sorted(set(PHYSICAL_MODELS) - set(BASE_MODELS)):
        n_rows = con.execute(f"SELECT COUNT(*) FROM main.{m}").fetchone()[0]
        cols = [
            r[0]
            for r in con.execute(
                f"SELECT name FROM pragma_table_info('{m}') WHERE type = 'VARCHAR'"
            ).fetchall()
            if not r[0].startswith("_dlt_")  # dlt bookkeeping, not model data
        ]
        for c in cols:
            rows = con.execute(
                f'SELECT "{c}", COUNT(*) FROM main.{m} GROUP BY 1 ORDER BY 2 DESC'
            ).fetchall()
            if not (len(rows) <= 12 and len(rows) * 2 <= n_rows):
                continue
            counts = ", ".join(f"{v!r}={n}" for v, n in rows)
            flag = "  <- UNIFORM: this column does not discriminate" if len(rows) == 1 else ""
            note(f"distribution {m}.{c}", f"{counts}{flag}")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    # --fixtures is passed by the harness and unused here: this scenario's
    # ground truth is the prompt's own values, already inlined above.
    ap.add_argument("--fixtures")
    ap.add_argument("--root")
    ap.add_argument("--trace", help="tool-call trace, for the ordering gate")
    ap.add_argument("positional", nargs="?")
    a = ap.parse_args()
    main(
        Path(a.root or a.positional or Path.cwd()).resolve(),
        Path(a.trace) if a.trace else None,
    )
