#!/usr/bin/env python3
"""Validate a closure built from a user-supplied rubric.

Three things beyond the ordinary closure checks:

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

import ast
import hashlib
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
SUPPLIED_WEIGHTS = {"50", "30", "20"}
SUPPLIED_THRESHOLDS = {"4.0", "2.5"}
SUPPLIED_VERDICTS = {"ADVANCE", "HOLD", "REJECT"}


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


def main(root: Path) -> None:
    root = root.resolve()

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

    leaked_thresholds = SUPPLIED_THRESHOLDS & lits
    check(
        "thresholds-not-hardcoded",
        not leaked_thresholds,
        f"supplied threshold(s) {sorted(leaked_thresholds)} appear as literals in "
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

    # ---- 2. the gap is surfaced, not defaulted ------------------------------
    # 'relevance of education' has no anchors in the prompt, and neither anchored
    # criterion defines 2/3/4. Silently inventing them is the defect.
    ledger = root / "data" / "nxd_decisions" / "nxd_decisions.csv"
    check(
        "decisions-ledger-present",
        ledger.is_file(),
        "a supplied procedure with an undefined scale is a ruling; "
        "data/nxd_decisions/nxd_decisions.csv is missing",
    )
    ledger_text = ledger.read_text().lower()
    check(
        "gap-surfaced",
        "blocked" in ledger_text or "education" in ledger_text,
        "the rubric's undefined scale (relevance of education has no anchors; "
        "no criterion defines 2/3/4) is not recorded in nxd_decisions",
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
    main(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd())
