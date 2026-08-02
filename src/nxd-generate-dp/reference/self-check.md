# The pre-handoff self-check script

## Contents

- What the phases are
- What this script does NOT cover
- The JSON report and the build record
- Where an expected value may come from
- The script
- Reading a failure

## What the phases are

The dry-run for Step 7 of nxd-generate-dp, in four phases:

- **Phase A — structural check of `models.py` and `spec.py`.** Parses both files
  with `ast` and checks them against the pinned DSL surface in
  [reference/nxd-spec-api.md](nxd-spec-api.md). Nothing is imported and nothing
  is executed, because the `nxd` wheel is an internal package on a private index
  and is NOT installable here — a real import raises
  `ModuleNotFoundError: No module named 'nxd'`.
- **Phase B — dry-run of the transform** against a scratch DuckDB: the
  supervisor's execution minus the kernel.
- **Phase C — closure-record gate** (Step 6a). A closure can be structurally
  valid and still be an insufficient handoff, and this is the phase that catches
  it. What changed with the snapshot design: sufficiency is now a
  **hash-checkable property**, not a prose discipline. The approved plan is
  byte-copied into the closure at generation as `dp-spec.approved.md`, and the
  phase checks:
  - `dp-spec.approved.md` is present at the closure root;
  - `dp-spec.lock.json` is present, parses, and carries schema
    `nxd-dp-spec-lock-v1`;
  - the snapshot's raw bytes hash to the lock's `snapshot_sha256` — the **tamper
    check**. The snapshot is evidence, and evidence edited after it was written
    is not evidence. This is the mechanical half of "once approved, the spec is
    frozen for that build", which used to be honour-system;
  - the lock records `spec_status_at_copy: approved` — a snapshot of an
    unapproved spec is a build nobody signed off;
  - `build-record.json` is present, parses, carries schema
    `nxd-build-record-v1`, and its `compiled_from` equals the lock's
    `spec_hash` — the record must describe a build of *this* plan;
  - `README.md` is present (the reopen recipe and the credential key names —
    the one thing a cold reader needs that is neither plan nor outcome);
  - every `resolved_refs[]` entry in the lock — the `prompt_ref` files mirrored
    in at snapshot time — exists in the closure with a matching sha256;
  - no closure file references a contract/design doc by a `../`-rooted path
    that escapes the closure. The snapshot **is** scanned: a `../`-rooted
    reference inside the approved plan is exactly the dangling pointer this
    design removes. No carve-out is needed anywhere, because the plan is
    *copied* rather than *pointed at*;
  - and — when `infra-profile.yaml` carries a populated `attributes:` list, i.e.
    a live credential in plaintext — that `.gitignore` and `SENSITIVE` exist and
    that `.gitignore` names `infra-profile.yaml`. Unchanged. The credential check
    reports missing FILES only; it never reads or echoes an attribute value,
    because a check that prints the secret it found turns a contained file leak
    into a transcript leak.

  Phase C checks the snapshot's **bytes**, which is sufficient *inside* the
  closure: those bytes are the ones the canonical hash was computed from, so a
  byte match means the canonical hash still holds by construction. The
  **canonical** hash — the one that answers "did the plan change?" — needs PyYAML
  and the live `dp-spec.md`, which lives outside the closure by design. Step 7
  therefore runs `python3 "$POCKET_HELPER_DIR/scripts/dp_diagnostics.py" lock verify <closure> --spec
  <dp-spec.md>` as well, and Phase C emits an informational diagnostic naming
  that command so a reader of the JSON can never mistake one check for the other.
  (Note: the naming invariant that Phase A enforces already requires every
  promised model to be in `PHYSICAL_MODELS`, so a model cannot be
  *promised-but-deferred*; a deferred contract belongs to a model not yet
  promised, carried in `contracts/<name>.md` — see Step 6a — until the model is
  authored and promised.)
- **Phase D — policy-boundary gate.** Checks that rulings are landed data the
  user can edit, not literals in transform code: `nxd_decisions`, if promised, is
  a **base** model backed by `data/` with a `status` column **and a `provenance`
  column**, each restricted to its fixed vocabulary, and no parameter in a landed
  policy CSV is duplicated as a literal in `transform/main.py`. A ledger
  generated from a Python literal *describes* the code instead of driving it —
  editing a row changes nothing, and the two silently diverge. `status` and
  `provenance` are checked independently because they answer different questions
  — *settled?* and *authored by whom?* — and a ledger carrying only the first
  cannot distinguish a weight the user supplied from a threshold you invented to
  make an underspecified rubric executable. The prose rules this enforces are in
  [derivation-plan.md](derivation-plan.md); Phase D is what makes them fire.

After the phases, the script prints a **distribution read-back** over every
derived model's classification columns. It is not a phase and it never fails the
run — it exists so a fabricated gate or verdict is visible rather than hidden
behind a green exit. Relay it (see "Reading a failure"). With `--record` it is
also written to the build record as data, because a read-back that only ever
existed in a scrollback is a read-back nobody can check later.

One script, one command, one exit code. What to check and how to read a failure
is in SKILL.md; this file is the runnable script.

The success banner says `C (context-completeness)` and that label is now a
deliberate half-truth: Phase C's meaning changed with the snapshot design, but
the line is keyed on byte-for-byte by `evals/run.py`'s deterministic check and by
every scenario checker, so the string is frozen and the script carries a comment
at the emitting line saying so. Accuracy of a label loses to stability of a
contract. Do not "fix" it.

## What this script does NOT cover

Read this before you trust a green result. Phase A is a *structural* check, not
a runtime one, and the gap is real:

- **It checks signatures against a pinned surface (`nxd` v0.41.139), not against
  the installed wheel.** If the DSL has drifted since that pin, Phase A enforces
  the pin, not reality. Re-derive the changed signature and update
  `nxd-spec-api.md` and this script together — the drift protocol is in that
  file's "Version pin and drift" section.
- **It cannot execute the builders.** Everything `nxd.spec` validates at build
  time is unexercised: value-shape errors inside a role blob, `FieldRef`
  resolution for `metric(of=...)`, and the supervisor's spec→YAML compilation at
  create time. **A closure can pass Phase A in full and still fail when the
  supervisor pins it.**
- **It cannot see dynamic constructs.** A schema entry built from a variable, a
  comprehension, or a `**` spread is reported as `unverified:
  <model>.<column>` and is NOT checked. The printed unverified list is the
  honest scope boundary — read it.
- **It says nothing about whether the semantics are right.** Whether a column
  should be a dimension, whether a metric's aggregation answers the question,
  whether the key is the real grain — no static check can know. Only closed-set
  violations (misspelled kwargs, unknown `Agg` members, unknown dtypes,
  misplaced roles, broken naming invariant) fail.

Phase B executes for real, so what it reports is what will happen — but it
covers only `transform/main.py`. A green Phase B says nothing about `spec.py` or
`models.py`, and the `unverified:` list is its own declared blind spot. Both are
recorded rather than merely printed: the blind spot goes into the report as
`struct.unverified` diagnostics, so it survives the scrollback.

Phase C's byte check is not the canonical hash. It answers *"was the in-closure
copy edited after it was written?"*, not *"did the plan change?"* — that second
question compares the live `dp-spec.md` against the lock and needs
`dp_diagnostics.py lock verify --spec`, which Step 7 runs separately.

## The JSON report and the build record

The default output is unchanged prose, and it must stay that way — `evals/run.py`
and every scenario checker key on those lines. Two flags add machine-readable
output on top of it:

```bash
python self_check.py --json                              # report to stdout
python self_check.py --json --record build-record.json   # and merge stages 1-3
```

- **`--json`** prints exactly one `nxd-diagnostic-report-v1` object and nothing
  else. The prose is suppressed, so stdout is parseable in full. Every phase
  emits the same `nxd-diagnostic-v1` shape — `{schema, stage, code, severity,
  owner, origin, path, message, evidence, fix?}` — differing only in which stage
  produced it: `s1_structure` (Phase A), `s2_transform` (Phase B and the
  read-back), `s3_closure` (Phases C and D, which share a stage because both are
  offline, both are agent-owned, and both self-heal; the `code` and `path` tell
  them apart).
- **`--record <path>`** merges those three stages into an existing
  `build-record.json` in place, along with the read-back and the Phase B row
  counts. The record is created by `dp_diagnostics.py record init` **before**
  this script runs — Phase C gates its presence — so a missing record is a real
  fault and is reported, never papered over by writing a fresh one here.

Exit codes: `0` clean, `1` a phase found something, `2` the closure could not be
read at all. The third is separate on purpose — "I looked and it is wrong" and "I
could not look" are different results, and a traceback for the second reads as a
broken checker rather than a closure you are standing outside of.

Three properties are worth knowing because they are what make the report
trustworthy rather than decorative:

- **A phase that did not run is `not_reached`, never `passed`.** The script still
  stops at the first failing phase — Phase B cannot run over malformed code — but
  under `--json` it emits the report *before* exiting, and the phases that never
  ran carry `status: "not_reached"` plus a `meta.stage_not_reached` diagnostic. A
  phase that produced no signal at all did not agree with you.
- **`severity` does not decide who hears about it; `owner` does.** Everything
  this script emits is `owner: agent` — structural faults and user-code runtime
  faults are yours to self-heal — except `closure.lock_status_not_approved`,
  which is `owner: user`, because only the user can approve a spec. The agent
  absorbs the rest and reports one plain line of outcome.
- **Phase B row counts are recorded under their own key, `phase_b_row_counts`,
  and are never merged with published counts.** One is a dry run against a
  temporary database; the other is what shipped. Collapsing them would let a
  scratch count stand in as evidence that the product has rows.

This script is copied into the closure and run there with a bare interpreter, so
it **cannot import `"$POCKET_HELPER_DIR/scripts/dp_diagnostics.py"`**. The code table at the top is an
inlined literal subset of that module's registry, and
`evals/tests/test_self_check_diagnostic_vocab.py` is what stops the two drifting.
Sharing the code by import would be wrong even where it is possible.

## Where an expected value may come from

SKILL.md's Step-3b invariant — *never restate the transform's arithmetic as an
assert* — extends to anything you add here, and the extension is the part that
gets violated. **An expected value comes from a landed `data/` file or from the
user's contract in `contracts/`. It never comes from the transform module or
from a copy of the transform's constants.**

Both halves matter, because complying with the first alone is the usual failure:

- `from transform.main import WEIGHTS, VERDICTS` and then asserting a weight is
  in `WEIGHTS` — fails only on a self-typo.
- `WEIGHTS = {...}` re-declared at the top of the checker, copied from the
  transform — no import, identical tautology.
- Recomputing a total with the transform's own formula over the transform's own
  constants — reproduces its arithmetic, including its errors.

None of these can detect a wrong score, a wrong gate, or a classification that
disagrees with the source. They are **internal-consistency checks**, and that is
what they must be called. Never narrate one as independent verification, and
never let a green exit stand in for "the numbers are right" — SELF-CHECK OK
means the closure is structurally sound and the transform ran, nothing more.

The good case is already the shipped one: Step-3b's Tier-1 asserts (declared-key
uniqueness, grain row count vs independently-read source rows) and Tier-2
(signed measure reconciliation in `Decimal`) all take their expected value from
the source, not from the code under test. Once a supplied rubric is landed as
data — see [derivation-plan.md](derivation-plan.md) — a check that reads the
rubric CSV is legitimately independent too.

## The script

Run from the closure root:

```bash
uv run --python 3.12 --with "dlt[duckdb]==1.28.2" --with "duckdb==1.5.4" \
  --with "pandas==2.3.3" python self_check.py
```

```python
# self_check.py
import ast, hashlib, json, re, sys, tempfile, time, traceback, types
from dataclasses import dataclass, field
from pathlib import Path

# ------------------------------------------------------------ diagnostics ---
# Every phase emits the same record shape ("nxd-diagnostic-v1") alongside the
# prose it has always printed. Two output paths, and they do not mix:
#   * default  — stdout is byte-for-byte what it was. evals/run.py's
#                deterministic check and every scenario checker key on those
#                lines, so a stray print here breaks graders, not just readers.
#   * --json   — ONE "nxd-diagnostic-report-v1" object on stdout and nothing
#                else, so it can be piped straight into a build record.
#
# This file is COPIED INTO THE CLOSURE and run there with a bare interpreter, so
# it can never import the Pocket diagnostics helper. The table below is an inlined
# literal subset of that module's registry; evals/tests/
# test_self_check_diagnostic_vocab.py is what keeps the two from drifting.
# severity and owner come from the table and are never chosen per call site:
# `owner` is the field that decides whether a human hears about a diagnostic at
# all, so a producer that could pick it could silence a blocker.
CODES = {}
def _codes(severity, owner, *codes):
    CODES.update({c: (severity, owner) for c in codes})

_codes("error", "agent",
       "struct.import_not_public_dsl", "struct.model_name_not_literal",
       "struct.model_no_description", "struct.view_empty_schema",
       "struct.view_field_not_metric_field", "struct.unknown_dtype",
       "struct.unknown_agg", "struct.agg_expression_forbidden",
       "struct.metric_in_model", "struct.metric_first_arg_not_agg",
       "struct.bad_kwarg", "struct.join_to_model_kwarg",
       "struct.primary_key_takes_no_args", "struct.metric_of_and_column",
       "struct.description_unreachable", "struct.role_no_description",
       "struct.join_target_missing", "struct.no_primary_key",
       "struct.semantic_tools_forbidden", "struct.bad_infra_profile",
       "struct.bad_script_path", "struct.missing_call", "struct.port_not_duckdb",
       "struct.port_no_storage", "struct.promise_of_view",
       "struct.malformed_service_ref",
       "struct.naming_invariant_promised_vs_models",
       "struct.naming_invariant_promised_vs_physical",
       "struct.base_models_vs_data_dirs")
_codes("info", "agent", "struct.unverified")
_codes("error", "agent",
       "runtime.import_failed", "runtime.transform_raised",
       "runtime.assert_failed", "runtime.base_models_mismatch",
       "runtime.transform_incomplete", "runtime.model_table_missing")
_codes("info", "agent", "runtime.row_count")
_codes("error", "agent",
       "closure.spec_snapshot_missing", "closure.lock_missing",
       "closure.lock_unparseable", "closure.lock_snapshot_byte_mismatch",
       "closure.build_record_missing", "closure.build_record_invalid",
       "closure.build_record_hash_mismatch", "closure.readme_missing",
       "closure.resolved_ref_missing", "closure.escaping_reference",
       "closure.gitignore_missing", "closure.sensitive_missing",
       "closure.gitignore_not_naming_profile",
       "closure.contract_not_wired", "closure.contract_verifier_missing",
       "closure.contract_verifier_malformed", "closure.contract_verifier_inert",
       "closure.contract_verifier_unreferenced",
       "closure.contract_verifier_secret", "closure.contract_duplicate_name",
       "closure.contract_spec_drift")
# The one closure.* code the AGENT cannot fix: a snapshot taken from a spec the
# user never approved is a governance fault, and only the user can approve.
_codes("error", "user", "closure.lock_status_not_approved")
_codes("info", "agent", "closure.canonical_hash_deferred")
_codes("error", "agent",
       "policy.decisions_not_base_model", "policy.decisions_csv_missing",
       "policy.decisions_column_missing", "policy.decisions_value_out_of_vocab",
       "policy.literal_duplicates_landed_value")
_codes("info", "agent", "semantic.distribution")
_codes("warning", "agent", "semantic.uniform_column", "semantic.absent_vocabulary")
_codes("info", "agent", "meta.stage_not_reached")

JSON_MODE = "--json" in sys.argv
RECORD_PATH = None
if "--record" in sys.argv:                 # no argparse: the closure's copy of
    _i = sys.argv.index("--record")        # this script stays small and its
    RECORD_PATH = (sys.argv[_i + 1]        # byte-identical twin stays readable
                   if _i + 1 < len(sys.argv) else "build-record.json")

DIAGS = []
STAGE_STATE = {"s1_structure": None, "s2_transform": None, "s3_closure": None}
STAGE_DETAIL = {"s1_structure": {}, "s2_transform": {}, "s3_closure": {}}
STAGE_AT = {}
READBACK = {"distribution": [], "absent": []}
ROW_COUNTS = []

# Same pattern the spec validator uses. A check that prints the secret it found
# turns a contained file leak into a transcript leak, and a JSON report is more
# copyable than a scrollback, not less — so message AND evidence go through it.
CREDENTIAL_VALUE_RE = re.compile(
    r"\b(password|passwd|secret|api[_-]?key|token|bearer|private[_-]?key)\b"
    r"\s*[:=]\s*\S+", re.IGNORECASE)

def redact(x):
    if isinstance(x, str):
        return CREDENTIAL_VALUE_RE.sub(lambda m: f"{m.group(1)}=<redacted>", x)
    if isinstance(x, dict):
        return {k: redact(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [redact(v) for v in x]
    return x

def say(*a, **k):
    """Prose stdout. Silent under --json so the report is the whole of stdout."""
    if not JSON_MODE:
        print(*a, **k)

def cpath(at):
    return f"closure:{at}" if at else ""

def diag(stage, code, message, *, path="", evidence=None, fix=None):
    sev, owner = CODES[code]
    d = {"schema": "nxd-diagnostic-v1", "stage": stage, "code": code,
         "severity": sev, "owner": owner, "origin": "tool_computed",
         "path": path, "message": redact(message),
         "evidence": redact(evidence or {})}
    if fix:
        d["fix"] = fix
    DIAGS.append(d)
    return d

def close_stage(stage, state, **detail):
    STAGE_STATE[stage] = state
    STAGE_AT[stage] = int(time.time() * 1000)
    STAGE_DETAIL[stage] = detail

def merge_record(path, stages):
    """Merge stages 1-3 into an existing build-record.json, in place.

    The record is created by `dp_diagnostics.py record init` BEFORE this script
    runs — Phase C gates its presence — so a missing record is a real fault and
    is reported rather than papered over by writing a fresh one here.
    """
    p = Path(path)
    try:
        rec = json.loads(p.read_text())
    except Exception as exc:
        say(f"record: {path} could not be read ({type(exc).__name__}: {exc}) — "
            "stages 1-3 NOT merged. Re-run generator lock/record setup with its "
            "resolved pocket_helper_dir before self_check.py.")
        return
    rec.setdefault("stages", {}).update(stages)
    if READBACK["distribution"] or READBACK["absent"]:
        rec["readback"] = READBACK
    if ROW_COUNTS:
        # Kept under its own key forever. Merging it with published_row_counts
        # would let a scratch-database dry run stand in as evidence that the
        # shipped product has rows.
        rec.setdefault("evidence", {})["phase_b_row_counts"] = {
            "origin": "agent_observed",
            "note": "scratch DuckDB dry run — NOT the published product",
            "models": ROW_COUNTS}
    p.write_text(json.dumps(rec, indent=2) + "\n")

def finish(exit_code):
    """Every exit goes through here, including a failing phase.

    Phases still stop at the first failure — Phase B cannot run over malformed
    code — but the report is emitted BEFORE exiting, with the phases that never
    ran carried as `not_reached`. `not_reached` is a distinct status from
    `passed`: a phase that produced no signal at all did not agree with you.
    """
    stages = {}
    for ordinal, s in ((1, "s1_structure"), (2, "s2_transform"),
                       (3, "s3_closure")):
        if STAGE_STATE[s] is None:
            diag(s, "meta.stage_not_reached",
                 f"{s} did not run and produced no signal at all — an earlier "
                 f"phase failed, or the closure could not be read.")
        ds = [d for d in DIAGS if d["stage"] == s]
        if STAGE_STATE[s] is None:
            status = "not_reached"
        elif STAGE_STATE[s] == "failed":
            status = "failed"
        elif any(d["severity"] == "warning" for d in ds):
            status = "passed_with_warnings"
        else:
            status = "passed"
        stages[s] = {"status": status, "ordinal": ordinal,
                     "at_unix_ms": STAGE_AT.get(s), "origin": "tool_computed",
                     "diagnostics": ds, "detail": STAGE_DETAIL[s]}
    if RECORD_PATH:
        merge_record(RECORD_PATH, stages)
    if JSON_MODE:
        counts = {"error": 0, "warning": 0, "info": 0}
        for d in DIAGS:
            counts[d["severity"]] += 1
        try:
            spec_hash = json.loads(
                Path("dp-spec.lock.json").read_text()).get("spec_hash")
        except Exception:
            spec_hash = None
        print(json.dumps({"schema": "nxd-diagnostic-report-v1",
                          "tool": "self_check", "target": str(Path.cwd()),
                          "ok": exit_code == 0, "counts": counts,
                          "spec_hash": spec_hash, "diagnostics": DIAGS},
                         indent=2))
    sys.exit(exit_code)

# ---------------------------------------------------------------- Phase A ---
# Structural check of models.py + spec.py against the pinned nxd.spec surface
# (reference/nxd-spec-api.md, nxd v0.41.139). No imports, no execution.

DTYPES = {
    "string", "boolean", "date", "date32", "date64", "double", "float",
    "float16", "float32", "float64", "int8", "int16", "int32", "int64",
    "uint", "uint8", "uint16", "uint32", "uint64", "number", "vector",
    "binary", "vector_embeddings", "timestamp", "decimal", "duration",
    "time32", "time64", "list", "list_view", "large_list", "large_list_view",
    "map", "dictionary", "struct", "variant",
}
AGGS = {"COUNT", "COUNT_DISTINCT", "SUM", "AVG", "MIN", "MAX", "EXPRESSION"}
KWARGS = {                      # role builder -> allowed keyword names
    "primary_key": set(),
    "dimension": {"name", "pii", "label", "description"},
    "join": {"to", "to_column", "cardinality", "to_data_product"},
    "metric": {"of", "name", "description", "boolean", "extra_dimensions",
               "column"},
    "field": {"roles", "description", "label", "name"},
    "metric_field": {"description", "name"},
}
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")

errors, unverified, unverified_at = [], [], []
def bad(code, msg, at=""):
    errors.append(msg)
    diag("s1_structure", code, msg, path=cpath(at))

def unv(msg, at=""):
    """A construct this static pass cannot see. Recorded, never a failure —
    the printed list is the honest scope boundary, and it belongs in the build
    record rather than in a scrollback nobody keeps."""
    unverified.append(msg)
    unverified_at.append(at)

def call_name(node):
    """Dotted or bare name of a Call's func, or None."""
    if not isinstance(node, ast.Call):
        return None
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None

def spine(node):
    """Every Call in a chained expression, outermost first."""
    out = []
    while isinstance(node, ast.Call):
        out.append(node)
        node = node.func.value if isinstance(node.func, ast.Attribute) else None
    return out

def literal_str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(
        node.value, str) else None

def desc_str(node):
    """Any authored description form: literal, f-string, or concatenation.

    Adjacent parenthesised literals are folded to one Constant by the parser,
    but an f-string is a JoinedStr and a runtime `a + b` is a BinOp. Both are
    legitimately-authored descriptions, so accept them here — the acceptance
    eval's has_description() accepts them too, and the two gates must agree or
    correctly-annotated code fails one of them.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value or None
    if isinstance(node, ast.JoinedStr):
        return ast.unparse(node)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return ast.unparse(node)
    return None

def check_kwargs(call, name, where):
    allowed = KWARGS[name]
    for kw in call.keywords:
        if kw.arg is None:
            unv(f"{where}: **spread into {name}()", where)
            continue
        if kw.arg in allowed:
            continue
        if name == "join" and kw.arg == "to_model":
            bad("struct.join_to_model_kwarg",
                f"{where}: join() takes to=, not to_model=", where)
        else:
            bad("struct.bad_kwarg",
                f"{where}: {name}() has no keyword '{kw.arg}' "
                f"(allowed: {sorted(allowed) or 'none'})", where)
    if name == "primary_key" and call.args:
        bad("struct.primary_key_takes_no_args",
            f"{where}: primary_key() takes no arguments", where)
    if name == "metric":
        if any(k.arg == "of" for k in call.keywords) and \
           any(k.arg == "column" for k in call.keywords):
            bad("struct.metric_of_and_column",
                f"{where}: metric() takes of= or column=, never both", where)
    # Annotation reach, both graded as failures. A description on the WRAPPER
    # is an attribute description: it lands in data_model and never reaches
    # describe_models, so the author believes they documented the concept and
    # did not. A MISSING description is the same defect by omission — and it
    # is the one the benchmark actually measured, so warning here while the
    # eval checks fail it would leave the only mechanical gate green on
    # precisely the defect this guidance exists to prevent.
    if name in ("field", "metric_field") and any(
            k.arg == "description" and desc_str(k.value) for k in call.keywords):
        # A wrapper description is a legal attribute description (it reaches
        # the structural data_model block). The defect is using it INSTEAD of
        # the role's, so only fail when the roles carry none — otherwise this
        # would block a legal API call that is not the mistake.
        roles = [a for a in call.args[1:] if isinstance(a, ast.Call)]
        for kw in call.keywords:          # documented roles=[...] form
            if kw.arg == "roles" and isinstance(kw.value, (ast.List, ast.Tuple)):
                roles += [e for e in kw.value.elts if isinstance(e, ast.Call)]
        describable = [r for r in roles if call_name(r) in ("dimension", "metric")]
        if not any(any(k.arg == "description" and desc_str(k.value)
                       for k in r.keywords) for r in describable):
            # Point at a fix that exists. With no dimension/metric role there
            # is nowhere to move the text to — primary_key()/join() take no
            # description — so the only remedy is to delete it.
            remedy = ("move it inside dimension(...) / metric(...)"
                      if describable else
                      "primary_key()/join() take no description — drop it")
            bad("struct.description_unreachable",
                f"{where}: description= on {name}() never reaches "
                f"describe_models and the role carries none — {remedy}", where)
    if name in ("dimension", "metric") and not any(
            k.arg == "description" and desc_str(k.value)
            for k in call.keywords):
        bad("struct.role_no_description",
            f"{where}: {name}() has no description= — it reaches "
            f"describe_models as a bare name the agent cannot choose on", where)

def check_dtype(node, where):
    """A call in dtype position must be a known data-type constructor."""
    n = call_name(node)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if n not in DTYPES:
            bad("struct.unknown_dtype",
                f"{where}: unknown data type '{n}()' — not in the pinned "
                f"nxd.spec.data_types surface", where)

def walk_roles(node, where, *, in_view):
    """Validate every role/dtype/Agg reference inside one schema entry."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) \
                and sub.value.id == "Agg":
            if sub.attr not in AGGS:
                bad("struct.unknown_agg",
                    f"{where}: Agg.{sub.attr} is not a member "
                    f"(allowed: {sorted(AGGS)})", where)
            elif sub.attr == "EXPRESSION":
                # A real API member, but out of scope for this generation path:
                # its SQL lives in the output PORT model's expressions={...} map,
                # which the desktop closure does not author. Reaching for it here
                # is always an attempt to dodge a derivation — the ruling belongs
                # in the transform as a physical column or row.
                bad("struct.agg_expression_forbidden",
                    f"{where}: Agg.EXPRESSION is outside this generation path — "
                    f"materialize the ruling as a physical column in the "
                    f"transform and aggregate that column with a normal Agg "
                    f"(see reference/derivation-plan.md)", where)
        if not isinstance(sub, ast.Call):
            continue
        n = call_name(sub)
        if n in KWARGS:
            check_kwargs(sub, n, where)
        if n == "metric":
            if not in_view:
                bad("struct.metric_in_model",
                    f"{where}: metric() inside a semantic_model schema — "
                    f"metrics are consume-time only, declare them as "
                    f"metric_field(metric(...)) on a semantic_view", where)
            if sub.args and not (isinstance(sub.args[0], ast.Attribute)
                                 and isinstance(sub.args[0].value, ast.Name)
                                 and sub.args[0].value.id == "Agg"):
                bad("struct.metric_first_arg_not_agg",
                    f"{where}: metric()'s first argument must be an Agg "
                    f"member (e.g. Agg.SUM), not a bare value", where)

def parse_models(src, path):
    """-> ({var: name}, {var: kind}, {name: joins}, {name: has_pk})"""
    tree = ast.parse(src, path)
    var_name, var_kind, joins, has_pk = {}, {}, {}, {}
    for imp in ast.walk(tree):
        if isinstance(imp, ast.ImportFrom) and (imp.module or "").startswith("nxd"):
            head = imp.module.split(".")
            if not (head[:2] == ["nxd", "spec"] and len(head) <= 3):
                bad("struct.import_not_public_dsl",
                    f"{path}: import from '{imp.module}' — public DSL only "
                    f"(nxd.spec / nxd.spec.data_types)", path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        chain = spine(node.value)
        if not chain:
            continue
        root = chain[-1]
        kind = call_name(root)
        if kind not in ("semantic_model", "semantic_view"):
            continue
        # The name may be positional or the documented name= keyword — the
        # vendored example corpus writes semantic_model(name=..., description=...)
        # throughout, and best_practices.md prefers it. Missing this shape does
        # not just skip the name check, it skips the model's fields entirely.
        name_node = (root.args[0] if root.args else
                     next((k.value for k in root.keywords if k.arg == "name"), None))
        model = literal_str(name_node) if name_node is not None else None
        if model is None or not SNAKE.match(model):
            shown = ast.unparse(name_node) if name_node is not None else "<none>"
            bad("struct.model_name_not_literal",
                f"{path}: {kind}() name must be a lowercase snake_case string "
                f"literal, got {shown}", path)
            continue
        var_name[target.id], var_kind[target.id] = model, kind
        joins.setdefault(model, []); has_pk[model] = False
        # Either authoring form counts: the chained .description(...) is the
        # verified one, but the description= constructor kwarg is pinned in
        # the documented signature and is what the shipped example corpus
        # uses, so rejecting it would fail correctly-authored models.
        if kind == "semantic_model" and not (
                any(call_name(c) == "description" and c.args
                    and desc_str(c.args[0]) for c in chain)
                or any(k.arg == "description" and desc_str(k.value)
                       for k in root.keywords)):
            bad("struct.model_no_description",
                f"{path}: semantic_model('{model}') declares no description "
                f"— both list_models and describe_model show it to the agent",
                f"{path}:{model}")
        in_view = kind == "semantic_view"
        for call in chain:
            if call_name(call) not in ("schema", "fields") or not call.args:
                continue
            schema = call.args[0]
            if not isinstance(schema, ast.Dict):
                unv(f"{model}: .schema() argument is not a dict literal",
                    f"{path}:{model}")
                continue
            if in_view and not schema.keys:
                bad("struct.view_empty_schema",
                    f"{path}: semantic_view('{model}') has an empty schema — "
                    f"this raises at build time", f"{path}:{model}")
            for k, v in zip(schema.keys, schema.values):
                col = literal_str(k) or "<dynamic>"
                where = f"{path}:{model}.{col}"
                if k is None:
                    unv(f"{model}: ** spread in .schema()", f"{path}:{model}")
                    continue
                entry_calls = ([v] if isinstance(v, ast.Call)
                               else list(v.elts) if isinstance(v, ast.Tuple) else [])
                if not entry_calls and not isinstance(v, ast.Tuple):
                    unv(f"{where}: schema value is "
                        f"{type(v).__name__}, not a call or tuple", where)
                    continue
                top = call_name(v) if isinstance(v, ast.Call) else None
                if in_view and isinstance(v, ast.Call) and top != "metric_field":
                    bad("struct.view_field_not_metric_field",
                        f"{where}: a semantic_view field must be "
                        f"metric_field(...), got {top}()", where)
                if top in ("field", "metric_field") and v.args:
                    check_dtype(v.args[0], where)
                elif top in DTYPES or (top and isinstance(v, ast.Call)
                                       and isinstance(v.func, ast.Name)):
                    check_dtype(v, where)
                if isinstance(v, ast.Tuple) and v.elts:
                    check_dtype(v.elts[0], where)
                walk_roles(v, where, in_view=in_view)
                for sub in ast.walk(v):
                    if call_name(sub) == "primary_key":
                        has_pk[model] = True
                    if call_name(sub) == "join":
                        tgt = (literal_str(sub.args[0]) if sub.args else
                               next((literal_str(k.value) for k in sub.keywords
                                     if k.arg == "to"), None))
                        if tgt:
                            joins[model].append((tgt, where))
    return var_name, var_kind, joins, has_pk

def parse_spec(src, path, var_name, var_kind):
    """-> set of promised model names"""
    tree = ast.parse(src, path)
    promised, modelled, saw = set(), set(), {"data_product": False,
                                             "script": False, "compute": False,
                                             "secrets": False, "port": False}
    if ".semantic_tools(" in src:
        bad("struct.semantic_tools_forbidden",
            f"{path}: .semantic_tools(...) is forbidden on desktop", path)

    # A custom contract's verifier is also a script(...).compute(...), so the
    # transform's rules cannot be applied to every script call in the file. Mark
    # the verifier scripts first: they are the ones reachable from a custom(...)
    # contract, and they are exempt from "must point at transform/main.py" and
    # do not satisfy the transform's own required-call set.
    verifier_scripts = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or call_name(node) != "verify":
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and call_name(sub) == "script":
                verifier_scripts.add(id(sub))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        n = call_name(node)
        if n == "data_product":
            saw["data_product"] = True
            ip = next((literal_str(k.value) for k in node.keywords
                       if k.arg == "infra_profile"), None)
            if ip != "desktop-local":
                bad("struct.bad_infra_profile",
                    f"{path}: data_product(infra_profile=...) must be the "
                    f"literal \"desktop-local\", got {ip!r}", path)
        elif n == "script":
            if id(node) in verifier_scripts:
                # A contract verifier, checked by the Phase C custom-contract
                # gate against contracts/, not by the transform's path rule.
                continue
            saw["script"] = True
            if literal_str(node.args[0] if node.args else None) != "transform/main.py":
                bad("struct.bad_script_path",
                    f"{path}: script() must point at \"transform/main.py\"", path)
        elif n in ("compute", "secrets"):
            # Only the TRANSFORM's .compute()/.secrets() satisfy the required
            # call set. A verifier's .compute(_compute) must not stand in for a
            # transform that never declared one.
            if not any(id(sub) in verifier_scripts
                       for sub in ast.walk(node) if isinstance(sub, ast.Call)):
                saw[n] = True
        elif n == "port":
            saw["port"] = True
            if literal_str(node.args[0] if node.args else None) != "duckdb":
                bad("struct.port_not_duckdb",
                    f"{path}: the output port must be named \"duckdb\"", path)
            if len(node.args) < 2 or call_name(node.args[1]) != "storage":
                bad("struct.port_no_storage",
                    f"{path}: .port(\"duckdb\", ...) second argument must be "
                    f"a storage(...) call", path)
        elif n in ("promise", "model") and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Name) and arg.id in var_name:
                (promised if n == "promise" else modelled).add(var_name[arg.id])
                if n == "promise" and var_kind[arg.id] == "semantic_view":
                    bad("struct.promise_of_view",
                        f"{path}: .promise({arg.id}) — {var_name[arg.id]} is a "
                        f"semantic_view; views are registered with .model(), "
                        f"never promised", path)
            elif any(call_name(c) == "custom" for c in spine(arg)):
                # .promise(custom("x")...verify(...)) — a custom contract, not a
                # models.py name. The root of the chain is the custom() call, so
                # match on the spine rather than the outermost call.
                pass  # validated by the Phase C custom-contract gate
            else:
                unv(f"{path}: .{n}() argument "
                    f"{ast.unparse(arg)} is not a models.py name", path)
    for key, msg in [("data_product", "no data_product(...) call"),
                     ("script", "no script(...) call"),
                     ("compute", "script() has no .compute(...)"),
                     ("secrets", "script() has no .secrets([...])"),
                     ("port", "no .port(...) call")]:
        if not saw[key]:
            bad("struct.missing_call", f"{path}: {msg}", path)
    for ref in re.findall(r'"(/infra-profile/[^"]*)"', src):
        if not re.fullmatch(r"/infra-profile/desktop-local#/services/[a-z0-9-]+", ref):
            bad("struct.malformed_service_ref",
                f"{path}: malformed service reference {ref!r} — expected "
                f"/infra-profile/desktop-local#/services/<name>", path)
    return promised, modelled

def model_constants(src):
    """BASE_MODELS / PHYSICAL_MODELS out of transform/main.py, statically."""
    tree, out = ast.parse(src, "transform/main.py"), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and \
                isinstance(node.targets[0], ast.Name) and \
                node.targets[0].id in ("BASE_MODELS", "PHYSICAL_MODELS"):
            try:
                out[node.targets[0].id] = list(ast.literal_eval(node.value))
            except ValueError:
                unv(f"transform/main.py: {node.targets[0].id} "
                    f"is not a literal", "transform/main.py")
    return out

# Exit 2 = could not read, distinct from exit 1 = found something. A traceback
# here reads as a broken checker; the closure is simply not where we are.
try:
    models_src = Path("models.py").read_text()
    spec_src = Path("spec.py").read_text()
    transform_src = Path("transform/main.py").read_text()
except OSError as exc:
    print(f"CANNOT READ — {exc}. Run self_check.py from the CLOSURE ROOT: "
          f"models.py, spec.py and transform/main.py must all be present.",
          file=sys.stderr)
    finish(2)

var_name, var_kind, joins, has_pk = parse_models(models_src, "models.py")
promised, modelled = parse_spec(spec_src, "spec.py", var_name, var_kind)

base_names = {n for v, n in var_name.items() if var_kind[v] == "semantic_model"}
for model, edges in joins.items():
    for tgt, where in edges:
        if tgt not in base_names:
            bad("struct.join_target_missing",
                f"{where}: join(to=\"{tgt}\") — no semantic_model of that name "
                f"in models.py", where)
for model in base_names:
    if not has_pk[model]:
        bad("struct.no_primary_key",
            f"models.py: semantic_model('{model}') declares no primary_key()",
            f"models.py:{model}")

consts = model_constants(transform_src)
physical = set(consts.get("PHYSICAL_MODELS", []))
if promised != base_names:
    bad("struct.naming_invariant_promised_vs_models",
        f"naming invariant: semantic_model names {sorted(base_names)} != "
        f"promised names {sorted(promised)}", "spec.py")
if physical and promised != physical:
    bad("struct.naming_invariant_promised_vs_physical",
        f"naming invariant: promised names {sorted(promised)} != "
        f"PHYSICAL_MODELS {sorted(physical)}", "transform/main.py")
if "BASE_MODELS" in consts:
    dirs = {d.name for d in Path("data").iterdir() if d.is_dir()}
    if set(consts["BASE_MODELS"]) != dirs:
        bad("struct.base_models_vs_data_dirs",
            f"BASE_MODELS {sorted(consts['BASE_MODELS'])} != data/ directories "
            f"{sorted(dirs)}", "transform/main.py")

for u, at in zip(unverified, unverified_at):
    say(f"unverified: {u}")
    diag("s1_structure", "struct.unverified", f"unverified: {u}", path=cpath(at))
if errors:
    say("\nPHASE A FAILED — structural check of models.py / spec.py:")
    for e in errors:
        say(f"  - {e}")
    close_stage("s1_structure", "failed",
                errors=len(errors), unverified=len(unverified))
    finish(1)
close_stage("s1_structure", "passed",
            models_counted=len(base_names), unverified=len(unverified))
say(f"phase A ok — {len(base_names)} semantic_model, "
    f"{len(modelled - base_names)} semantic_view, "
    f"{len(unverified)} unverified entries")

# ---------------------------------------------------------------- Phase B ---
# Dry-run of transform/main.py against a scratch DuckDB. This one EXECUTES.
# Everything it reports is what will happen on the supervisor, so a failure
# here is unambiguously the generated code — never the environment. There is
# no kernel and no network in this phase to blame.

@dataclass
class DuckDbOutput:
    path: str; schema: str; model_tables: dict; models: dict = field(default_factory=dict)

berrors, btracebacks = [], []
def berr(code, msg, at="", ev=None, tb=""):
    berrors.append(msg)
    btracebacks.append(tb)
    ev = dict(ev or {})
    if tb:
        ev["traceback"] = tb
    diag("s2_transform", code, msg, path=cpath(at), evidence=ev)

def fail_b():
    say("\nPHASE B FAILED — transform dry-run (this EXECUTED: what it reports "
        "is what will happen):")
    for e, tb in zip(berrors, btracebacks):
        say(f"  - {e}")
        if tb:
            say("".join(f"      {ln}\n" for ln in tb.strip().splitlines()), end="")
    close_stage("s2_transform", "failed", errors=len(berrors))
    finish(1)

nxd = types.ModuleType("nxd"); core = types.ModuleType("nxd.core")
ctx = types.ModuleType("nxd.core.context"); ctx.DuckDbOutput = DuckDbOutput; dp = types.SimpleNamespace(
    on_transform=lambda *a, **k: (lambda fn: fn), main=lambda: None)
nxd.data_product, nxd.core, core.context = dp, core, ctx
sys.modules.update({"nxd": nxd, "nxd.core": core, "nxd.core.context": ctx})

sys.path.insert(0, ".")
try:
    from transform.main import BASE_MODELS, PHYSICAL_MODELS, ingest  # noqa: E402
except Exception as exc:
    berr("runtime.import_failed",
         f"transform/main.py: import failed — {type(exc).__name__}: {exc}",
         "transform/main.py", tb=traceback.format_exc())
    fail_b()

DIRS = [d.name for d in sorted(Path("data").iterdir()) if d.is_dir()]
# Only BASE models are backed by data/. Derived models are landed by the
# transform and appear in PHYSICAL_MODELS with no directory of their own.
if set(BASE_MODELS) != set(DIRS):
    berr("runtime.base_models_mismatch",
         f"base models must match data/: BASE_MODELS {sorted(set(BASE_MODELS))} "
         f"!= data/ directories {sorted(set(DIRS))}", "transform/main.py",
         {"expected": sorted(set(DIRS)), "actual": sorted(set(BASE_MODELS))})
if not set(BASE_MODELS) <= set(PHYSICAL_MODELS):
    berr("runtime.base_models_mismatch",
         f"base models must be promised: "
         f"{sorted(set(BASE_MODELS) - set(PHYSICAL_MODELS))} are in BASE_MODELS "
         f"but not in PHYSICAL_MODELS", "transform/main.py")
if berrors:
    fail_b()
run = Path(tempfile.mkdtemp())
# model_tables comes from PHYSICAL_MODELS, never the data/ listing: a map built
# from directories KeyErrors the moment a derived model resolves its table name.
out = DuckDbOutput(path=str(run / "data.duckdb"), schema="main",
                   model_tables={m: m for m in PHYSICAL_MODELS})
try:
    ingest(duckdb=out, secrets={"csv_source": str(Path("data").resolve())})
except AssertionError as exc:
    # A fired assert is the transform's OWN invariant rejecting the data it
    # produced. That is the check working, not the check being wrong.
    berr("runtime.assert_failed",
         f"transform/main.py: an assert fired during the dry run — {exc}",
         "transform/main.py", tb=traceback.format_exc())
except Exception as exc:
    berr("runtime.transform_raised",
         f"transform/main.py: {type(exc).__name__}: {exc}",
         "transform/main.py", tb=traceback.format_exc())
if berrors:
    fail_b()
import duckdb
con = duckdb.connect(out.path, read_only=True)
for m in PHYSICAL_MODELS:  # unquoted main.<name> — the invariant, physically
    try:
        n_rows = con.execute(f"SELECT COUNT(*) FROM main.{m}").fetchone()[0]
    except Exception as exc:
        berr("runtime.model_table_missing",
             f"main.{m} is promised but is not queryable after the transform — "
             f"{type(exc).__name__}: {exc}", "transform/main.py", {"model": m})
        continue
    say(m, n_rows)
    ROW_COUNTS.append({"table": m, "row_count": n_rows})
    diag("s2_transform", "runtime.row_count", f"{m}: {n_rows} rows",
         path=cpath(f"transform/main.py:{m}"),
         evidence={"model": m, "count": n_rows})
if not (run / ".transform-complete").exists():
    berr("runtime.transform_incomplete",
         "the transform returned without writing .transform-complete — it did "
         "not finish", "transform/main.py")
if berrors:
    fail_b()
close_stage("s2_transform", "passed",
            models_counted=len(PHYSICAL_MODELS), unverified=len(unverified))
say(f"phase B ok — transform dry-run EXECUTED; models.py/spec.py checked "
    f"STRUCTURALLY against the pinned nxd v0.41.139 DSL surface (not "
    f"executed — no nxd wheel installable here); {len(unverified)} "
    f"unverified entries listed above. A spec fault only the real wheel or "
    f"the supervisor's spec compilation can raise still reaches handoff.")

# ---------------------------------------------------------------- Phase C ---
# Closure-record gate (Step 6a). The closure must be a SUFFICIENT handoff, and
# after this change that is a HASH-CHECKABLE property rather than a prose
# discipline: the approved spec is byte-copied in as dp-spec.approved.md, the
# lock carries its hash and the compiler version, and build-record.json says
# which spec the closure was compiled from. A structurally valid closure can
# still be uncontinuable if the plan it was built from lives in ../../some-doc.md
# — copied, never pointed at, is what removes that failure mode.
cerrors = []
def cerr(code, msg, at="", ev=None):
    cerrors.append(msg)
    diag("s3_closure", code, msg, path=cpath(at), evidence=ev)

# C11 first, so it is in the report whatever else happens: Phase C compares the
# snapshot's BYTES, which is sufficient inside the closure (the bytes are the
# ones the canonical hash was computed from) and needs nothing but hashlib. The
# CANONICAL hash — the one that answers "did the plan change?" — needs PyYAML
# and the live IR, both of which are outside the closure.
diag("s3_closure", "closure.canonical_hash_deferred",
     "Phase C checked the snapshot's raw bytes against dp-spec.lock.json. The "
     "canonical (semantic) hash and the comparison against the live dp-spec.md "
     "are NOT checked here — re-run generator canonical lock verification with its "
     "resolved pocket_helper_dir for that.",
     path=cpath("dp-spec.lock.json"))

# C1 / C2 — the approved plan and its lock must both be in the closure.
snap = Path("dp-spec.approved.md")
snap_bytes = snap.read_bytes() if snap.exists() else None
if snap_bytes is None:
    cerr("closure.spec_snapshot_missing",
         "dp-spec.approved.md is missing from the closure root — the closure "
         "carries no copy of the approved plan it was compiled from, so a cold "
         "reader cannot tell what it was supposed to build. Byte-copy the "
         "approved dp-spec.md in at generation (Step 6a).", "dp-spec.approved.md")
lock = None
lockp = Path("dp-spec.lock.json")
if not lockp.exists():
    cerr("closure.lock_missing",
         "dp-spec.lock.json is missing from the closure root — without it the "
         "snapshot is an unattributed copy: no hash, no compiler version, "
         "nothing to check it against. Run `dp_diagnostics.py lock write`.",
         "dp-spec.lock.json")
else:
    try:
        lock = json.loads(lockp.read_text())
        if not isinstance(lock, dict):
            raise ValueError("not a JSON object")
        if lock.get("schema") != "nxd-dp-spec-lock-v1":
            raise ValueError(f"schema is {lock.get('schema')!r}, expected "
                             f"'nxd-dp-spec-lock-v1'")
    except Exception as exc:
        lock = None
        cerr("closure.lock_unparseable",
             f"dp-spec.lock.json could not be read as a lock file — "
             f"{type(exc).__name__}: {exc}", "dp-spec.lock.json")

# C3 — tamper check. The snapshot is EVIDENCE; evidence edited after it was
# written is not evidence. This is the mechanical half of "once approved, the
# spec is frozen for that build", which used to be honour-system.
if lock is not None and snap_bytes is not None:
    got = hashlib.sha256(snap_bytes).hexdigest()
    want = lock.get("snapshot_sha256")
    if got != want:
        cerr("closure.lock_snapshot_byte_mismatch",
             f"dp-spec.approved.md does not match dp-spec.lock.json "
             f"snapshot_sha256 — the in-closure copy was edited after it was "
             f"written. The plan a build was compiled from is not editable "
             f"in place: change the live dp-spec.md, re-approve, regenerate.",
             "dp-spec.approved.md", {"expected": want, "actual": got})

# C4 — a snapshot of an unapproved spec is a build nobody signed off.
if lock is not None and lock.get("spec_status_at_copy") != "approved":
    cerr("closure.lock_status_not_approved",
         f"dp-spec.lock.json records spec_status_at_copy="
         f"{lock.get('spec_status_at_copy')!r} — the closure was generated from "
         f"a spec that was not approved. Approval is what gets copied and "
         f"hashed; without it nothing here was signed off.", "dp-spec.lock.json",
         {"expected": "approved", "actual": lock.get("spec_status_at_copy")})

# C5 / C6 — the build record exists and names the SAME plan as the lock. It is
# generated (`dp_diagnostics.py record init`), never hand-authored, and it must
# exist before this phase runs because this phase is one of its writers.
record = None
recp = Path("build-record.json")
if not recp.exists():
    cerr("closure.build_record_missing",
         "build-record.json is missing from the closure root — outcomes "
         "(attempts, concessions, blockers, read-back) have nowhere to land, "
         "so a green run would be indistinguishable from a green run that "
         "conceded something. Run `dp_diagnostics.py record init` at "
         "generation, before self_check.py.", "build-record.json")
else:
    try:
        record = json.loads(recp.read_text())
        if not isinstance(record, dict):
            raise ValueError("not a JSON object")
        if record.get("schema") != "nxd-build-record-v1":
            raise ValueError(f"schema is {record.get('schema')!r}, expected "
                             f"'nxd-build-record-v1'")
    except Exception as exc:
        record = None
        cerr("closure.build_record_invalid",
             f"build-record.json could not be read as a build record — "
             f"{type(exc).__name__}: {exc}", "build-record.json")
if lock is not None and record is not None and \
        record.get("compiled_from") != lock.get("spec_hash"):
    cerr("closure.build_record_hash_mismatch",
         f"build-record.json compiled_from does not equal dp-spec.lock.json "
         f"spec_hash — the record describes a build of a DIFFERENT plan than "
         f"the one snapshotted here. Regenerate rather than reconciling by "
         f"hand.", "build-record.json",
         {"expected": lock.get("spec_hash"),
          "actual": record.get("compiled_from")})

# C7 — the reopen recipe. It is the one thing a cold reader needs that is
# neither plan (the snapshot) nor outcome (the record).
if not Path("README.md").exists():
    cerr("closure.readme_missing",
         "README.md is missing from the closure root — it carries the reopen "
         "recipe and the credential key names, and nothing else does.",
         "README.md")

# C8 — prompt_ref files are relative to the LIVE IR, so a byte copy would carry
# a path resolving outside the closure. They are mirrored in at snapshot time
# and recorded in the lock; here we check the mirror actually landed.
for ref in (lock or {}).get("resolved_refs") or []:
    rel = (ref or {}).get("closure_path") or ""
    rp = Path(rel) if rel else None
    if not rel or not rp.exists():
        cerr("closure.resolved_ref_missing",
             f"dp-spec.approved.md references {(ref or {}).get('spec_ref')!r} "
             f"and the lock says it was mirrored to {rel!r}, but that file is "
             f"not in the closure — the snapshot points at nothing.", rel)
        continue
    got = hashlib.sha256(rp.read_bytes()).hexdigest()
    if got != ref.get("sha256"):
        cerr("closure.resolved_ref_missing",
             f"{rel} does not match the sha256 recorded in dp-spec.lock.json — "
             f"the mirrored copy was edited after it was written.", rel,
             {"expected": ref.get("sha256"), "actual": got})

# C9 — escape scan. Any closure file that references a design/contract doc by a
# path escaping the closure (a ../-rooted markdown reference) is a dangling
# cross-boundary pointer. The snapshot IS scanned: a ../-rooted reference inside
# the approved plan is exactly the dangling pointer this design removes, and no
# carve-out is needed anywhere because the IR is COPIED rather than pointed at.
ESCAPE = re.compile(r"\.\.(?:/[^\s\)\"']*)+\.md", re.IGNORECASE)
scan = ["README.md", "dp-spec.approved.md", "spec.py", "models.py",
        "transform/main.py"]
# rglob, not glob: contracts/ now holds expectations/ and promises/ subtrees as
# well as the flat contracts/<name>.md, and a verifier that points out of the
# closure escapes just as effectively from one level down.
scan += [str(p) for p in Path(".").rglob("contracts/*")]
scan += [str(p) for p in Path(".").rglob("contracts/*/*")]
for rel in scan:
    p = Path(rel)
    if not p.is_file():
        continue
    for m in ESCAPE.findall(p.read_text()):
        cerr("closure.escaping_reference",
             f"{rel}: references '{m}' — a contract/design path that escapes "
             f"the closure. Materialize it inside the closure "
             f"(dp-spec.approved.md / contracts/<name>.md / inert derived "
             f"model), never a ../ pointer.", rel, {"found": m})

# C10 — sensitivity artifacts. The trigger is STRUCTURAL: a *-source service
# carrying a populated `attributes:` list holds a live credential in plaintext.
# A CSV or file source keeps `attributes: []` and is exempt, so this cannot
# false-positive on a healthy local closure. Names the missing FILES only —
# never reads or echoes an attribute value, because a check that prints the
# secret it found turns a contained file leak into a transcript leak.
profile = Path("infra-profile.yaml")
if profile.exists():
    text = profile.read_text()
    # A populated attributes list = `attributes:` followed by a `- ` item before
    # the next key at the same or shallower indent. `attributes: []` never matches.
    # Match every YAML spelling of a populated list, because a gate that only
    # recognises the shipped templates is not the structural check it claims to
    # be — an improvised profile carries exactly the same live credential:
    #   block, indented      `attributes:` / `  - key: ...`   (what templates emit)
    #   block, zero-indent   `attributes:` / `- key: ...`     (also valid YAML)
    #   inline flow          `attributes: [{key: ...}]`
    # `attributes: []` and `attributes: [ ]` must NOT match in any form.
    has_secret = (
        re.search(r"^\s*attributes:\s*\n\s*-\s", text, re.MULTILINE) is not None
        or re.search(r"^\s*attributes:\s*\[\s*[^\s\]]", text, re.MULTILINE) is not None
    )
    if has_secret:
        for name, code, why in (
            (".gitignore", "closure.gitignore_missing",
             "git will happily commit infra-profile.yaml without it"),
            ("SENSITIVE", "closure.sensitive_missing",
             "a cold reader gets no warning before opening the closure"),
        ):
            if not Path(name).exists():
                cerr(code,
                     f"{name} is missing, but infra-profile.yaml carries a populated "
                     f"`attributes:` list (a live credential in plaintext) — {why}. "
                     f"See reference/database-source.md, 'Sensitivity artifacts'.",
                     name)
        gi = Path(".gitignore")
        if gi.exists() and "infra-profile.yaml" not in gi.read_text():
            cerr("closure.gitignore_not_naming_profile",
                 ".gitignore exists but does not ignore infra-profile.yaml — the one "
                 "file that must never be committed. Ignore it by name, never `*`.",
                 ".gitignore")

# C12 — the custom-contract gate. A `## expectations` / `## promises` entry in
# the approved spec compiles to an executable verifier under contracts/. This
# proves the compilation happened and produced something that can actually
# fail: a contract that parses but can never return FAILED is decorative, and a
# decorative contract is worse than none — it reports a guarantee as enforced
# while enforcing nothing.
#
# The gate is STRUCTURAL and offline. A pass means every declared contract is
# wired once, names a verifier that exists under contracts/, and that verifier
# is shaped to run. It does NOT mean the verifier was executed against data.
CONTRACT_DIRS = {"expectations": "pre_transform", "promises": "post_transform"}
SECRET_LITERAL = re.compile(
    r"(?i)\b(api[_-]?key|password|passwd|token|secret)\s*=\s*[\"']")


def _verify_scripts(tree):
    """-> ({contract name: verifier path}, unnamed count, duplicate names).

    `custom("x").model(m).verify(script("p").compute(c))` is one call chain, so
    the verify() that belongs to a given custom() is the INNERMOST one whose
    subtree contains it. Matching on "any verify() in the file" would associate
    the wrong path as soon as a closure declares a second contract.
    """
    found, unnamed, dupes = {}, 0, []
    verifies = [n for n in ast.walk(tree)
                if isinstance(n, ast.Call) and call_name(n) == "verify"]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or call_name(node) != "custom":
            continue
        cname = literal_str(node.args[0] if node.args else None)
        if cname is None:
            unnamed += 1
            continue
        # Smallest enclosing verify() — by node count, so a nested chain picks
        # its own and never a sibling contract's.
        best, best_size = None, None
        for v in verifies:
            subtree = list(ast.walk(v))
            if not any(sub is node for sub in subtree):
                continue
            if best_size is None or len(subtree) < best_size:
                best, best_size = v, len(subtree)
        path = None
        if best is not None:
            for sub in ast.walk(best):
                if isinstance(sub, ast.Call) and call_name(sub) == "script":
                    path = literal_str(sub.args[0] if sub.args else None)
                    break
        if cname in found:
            dupes.append(cname)
        found[cname] = path
    return found, unnamed, dupes


try:
    _spec_tree = ast.parse(spec_src, "spec.py")
except SyntaxError:
    _spec_tree = None          # Phase A already reported it; do not double-report

if _spec_tree is not None:
    contracts, unnamed, dupes = _verify_scripts(_spec_tree)

    if unnamed:
        cerr("closure.contract_not_wired",
             f"spec.py: {unnamed} custom(...) contract(s) have a non-literal "
             f"name. The name selects the verifier file, so it must be a string "
             f"literal.", "spec.py", {"count": unnamed})
    for d in sorted(set(dupes)):
        cerr("closure.contract_duplicate_name",
             f"spec.py: two custom contracts are named {d!r} — the name selects "
             f"the generated verifier file, so one silently overwrites the "
             f"other. Names are unique across expectations AND promises.",
             "spec.py", {"found": d})

    referenced = set()
    for cname, vpath in sorted(contracts.items()):
        if not vpath:
            cerr("closure.contract_not_wired",
                 f"spec.py: custom({cname!r}) has no "
                 f".verify(script(...).compute(_compute)) — a contract with no "
                 f"verifier declares a guarantee nothing checks.",
                 "spec.py", {"contract": cname})
            continue
        # Containment before touching the path: a verifier resolved outside the
        # closure is the cross-boundary pointer C9 exists to stop.
        if vpath.startswith("/") or ".." in Path(vpath).parts or \
                not vpath.startswith("contracts/"):
            cerr("closure.contract_not_wired",
                 f"spec.py: custom({cname!r}) verifier {vpath!r} must stay under "
                 f"contracts/ inside the closure.", "spec.py",
                 {"contract": cname, "found": vpath})
            continue
        referenced.add(vpath)
        vp = Path(vpath)
        if not vp.is_file():
            cerr("closure.contract_verifier_missing",
                 f"{vpath}: referenced by custom({cname!r}) but the file does "
                 f"not exist.", vpath, {"contract": cname})
            continue
        vsrc = vp.read_text()
        try:
            vtree = ast.parse(vsrc, vpath)
        except SyntaxError as exc:
            cerr("closure.contract_verifier_malformed",
                 f"{vpath}: verifier does not parse ({exc.msg}).", vpath,
                 {"contract": cname})
            continue

        verifiers = [n for n in ast.walk(vtree)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and any(call_name(d) == "on_verify"
                             for d in n.decorator_list
                             if isinstance(d, ast.Call))]
        if len(verifiers) != 1:
            cerr("closure.contract_verifier_malformed",
                 f"{vpath}: needs exactly one @data_product.on_verify() "
                 f"function, found {len(verifiers)}. script(...) executes the "
                 f"whole file, so the contract name cannot select among "
                 f"several.", vpath, {"contract": cname, "found": len(verifiers)})
            continue
        if isinstance(verifiers[0], ast.AsyncFunctionDef):
            cerr("closure.contract_verifier_malformed",
                 f"{vpath}: the verifier is `async def`. Pocket does not await "
                 f"verifier functions, so an async verifier never runs and the "
                 f"contract silently passes.", vpath, {"contract": cname})
            continue
        if not any(isinstance(n, ast.If) and "__main__" in ast.dump(n.test)
                   and any(isinstance(s, ast.Expr)
                           and isinstance(s.value, ast.Call)
                           and call_name(s.value) == "verify"
                           for s in ast.walk(n))
                   for n in vtree.body):
            cerr("closure.contract_verifier_malformed",
                 f"{vpath}: needs a module-level "
                 f"`if __name__ == \"__main__\": data_product.verify()` guard — "
                 f"without it script(...) imports the file and checks nothing.",
                 vpath, {"contract": cname})
            continue

        # Inert: a verifier that cannot fail. It must be able to return FAILED,
        # and that return must sit behind a real (non-constant) condition — an
        # `if True:` branch reads as a check and is dead code.
        body = ast.dump(verifiers[0])
        can_fail = "FAILED" in vsrc
        live_branch = any(
            isinstance(n, ast.If) and not isinstance(n.test, ast.Constant)
            for n in ast.walk(verifiers[0]))
        if not can_fail or not live_branch or "PASS" not in vsrc:
            cerr("closure.contract_verifier_inert",
                 f"{vpath}: the verifier can never fail — it must return "
                 f"VerifyResultEnum.FAILED behind a real condition and PASS "
                 f"otherwise. A contract that always passes reports the "
                 f"guarantee as enforced while enforcing nothing.",
                 vpath, {"contract": cname})
        if SECRET_LITERAL.search(vsrc):
            cerr("closure.contract_verifier_secret",
                 f"{vpath}: contains a literal secret-like assignment. "
                 f"Credentials reach a closure through the infra profile, "
                 f"never inline in a verifier.", vpath, {"contract": cname})

    # Every file under contracts/*/ must be reachable from spec.py. An
    # unreferenced verifier is the decorative case in its purest form: it looks
    # like an enforced guarantee to a reader and never executes.
    for sub in sorted(CONTRACT_DIRS):
        d = Path("contracts") / sub
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*.py")):
            if p.name == "__init__.py":
                continue
            if str(p) not in referenced:
                cerr("closure.contract_verifier_unreferenced",
                     f"{p}: not referenced by any custom(...) in spec.py — a "
                     f"verifier nothing wires never runs.", str(p))

    # The closure's contracts must be exactly the approved spec's. A contract in
    # the closure that no spec section declares is a guarantee the user never
    # approved; one in the spec with no verifier was silently dropped.
    if snap_bytes is not None:
        spec_named = set()
        section = None
        for line in snap_bytes.decode("utf-8", "replace").splitlines():
            if line.startswith("## "):
                section = line[3:].strip().lower()
            elif section in CONTRACT_DIRS:
                m = re.match(r"\s*-\s+name:\s*(\S+)", line)
                if m:
                    spec_named.add(m.group(1).strip("\"'"))
        missing = spec_named - set(contracts)
        extra = set(contracts) - spec_named
        if missing:
            cerr("closure.contract_spec_drift",
                 f"dp-spec.approved.md declares contract(s) {sorted(missing)} "
                 f"that spec.py does not wire — an approved guarantee was "
                 f"dropped during generation.", "spec.py",
                 {"missing": sorted(missing)})
        if extra:
            cerr("closure.contract_spec_drift",
                 f"spec.py wires contract(s) {sorted(extra)} that "
                 f"dp-spec.approved.md does not declare — a guarantee the user "
                 f"never approved. Contracts originate in the IR.",
                 "spec.py", {"extra": sorted(extra)})

if cerrors:
    say("\nPHASE C FAILED — closure-record gate (approved spec snapshot, lock, "
        "build record):")
    for e in cerrors:
        say(f"  - {e}")
    close_stage("s3_closure", "failed", errors=len(cerrors))
    finish(1)
say("phase C ok — approved spec snapshot + lock present, no closure-escaping "
    "contract references")

# ---------------------------------------------------------------- Phase D ---
# Policy-boundary gate. A ruling is landed data the user can edit, never a
# literal in transform code. Both halves are checked, because complying with
# either alone leaves the defect intact:
#   (a) nxd_decisions, if promised, is a BASE model backed by data/ with a
#       status column AND a provenance column — not a derived model generated
#       from a Python literal, which produces a ledger that DESCRIBES code
#       rather than driving it. status and provenance are orthogonal axes
#       (settled-or-not vs authored-by), so both are required: a ledger with
#       only status cannot tell a weight the user supplied from a threshold the
#       agent invented to fill an underspecified rubric;
#   (b) no value in a landed policy CSV also appears as a literal in
#       transform/main.py — a duplicated threshold silently diverges from the
#       row that claims to be editable.
# Ground truth is the closure's own landed data, so this needs no fixture.
# Phase D shares stage s3_closure with Phase C: both are offline, both are
# agent-owned, both self-heal. The code and the path tell them apart.
derrors = []
dcodes = []
def derr(code, msg, at=""):
    """Buffer a Phase D finding WITH its code, in-block.

    Deliberately self-contained: evals/tests/test_policy_boundary_phase_d.py
    slices this phase out between the derrors initialiser and the reporting
    branch and runs it standalone, so anything Phase D calls must be defined
    between those two lines. Diagnostics are built in the reporting block below,
    which is outside the slice.
    """
    dcodes.append((code, at))
    derrors.append(msg)

# Use the values Phase B IMPORTED, not the statically-parsed ones: the template
# writes PHYSICAL_MODELS = BASE_MODELS + DERIVED_MODELS, which is an expression
# rather than a literal, so the static reader reports it `unverified` and a gate
# keyed on it would silently never fire.
if "nxd_decisions" in set(PHYSICAL_MODELS):
    if "nxd_decisions" not in set(BASE_MODELS):
        derr("policy.decisions_not_base_model",
            "nxd_decisions is promised but is not in BASE_MODELS — it is being "
            "generated in the transform. A ledger built from a Python literal "
            "describes the code instead of driving it: editing a row changes "
            "nothing. Write data/nxd_decisions/nxd_decisions.csv and land it "
            "like any other base model (reference/derivation-plan.md).",
            "transform/main.py")
    else:
        led = Path("data/nxd_decisions/nxd_decisions.csv")
        if not led.exists():
            derr("policy.decisions_csv_missing",
                 "nxd_decisions is in BASE_MODELS but "
                 "data/nxd_decisions/nxd_decisions.csv is missing.",
                 "data/nxd_decisions/nxd_decisions.csv")
        else:
            import csv as _csv
            with led.open(newline="") as fh:
                lrows = list(_csv.DictReader(fh))
            # status and provenance are checked INDEPENDENTLY: they are separate
            # axes, so a missing provenance column must not skip status
            # validation (or the reverse). Each column: present, then in-vocab.
            LEDGER_VOCAB = {
                "status": ({"confirmed", "proposed", "blocked"},
                           "status is how a user tells a settled ruling from an "
                           "open one"),
                "provenance": ({"user_confirmed", "agent_authored",
                                "source_derived", "deferred"},
                               "provenance is how a reviewer tells a value the "
                               "USER supplied from one the AGENT invented to "
                               "fill an underspecified rubric — status does not "
                               "carry that, it is a different axis"),
            }
            for lcol, (okvals, why) in LEDGER_VOCAB.items():
                if lrows and lcol not in lrows[0]:
                    derr("policy.decisions_column_missing",
                        f"nxd_decisions.csv has no {lcol!r} column (found "
                        f"{sorted(lrows[0])}). {why}. Allowed values are "
                        f"{sorted(okvals)} (reference/derivation-plan.md).",
                        f"data/nxd_decisions/nxd_decisions.csv:{lcol}")
                    continue
                badv = {(r[lcol] or "").strip() for r in lrows} - okvals
                if badv:
                    derr("policy.decisions_value_out_of_vocab",
                        f"nxd_decisions.{lcol} has {sorted(badv)}; allowed "
                        f"values are {sorted(okvals)}. The vocabulary is fixed: "
                        f"a value outside it is not queryable as a class.",
                        f"data/nxd_decisions/nxd_decisions.csv:{lcol}")

# (b) A policy value that is landed AND hardcoded is a divergence waiting to
# happen. Only scan CSVs whose model name looks like landed policy, and only
# compare distinctive values: short/common tokens ("1", "US", "PASS") collide by
# coincidence, and flagging those would make this unreliable.
POLICY_HINT = ("rubric", "weight", "threshold", "band", "anchor", "verdict",
               "scale", "policy", "gate", "criteri")
tsrc = Path("transform/main.py").read_text()
tlits = set()
for node in ast.walk(ast.parse(tsrc)):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            tlits.add(node.value.strip())
        elif isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            tlits.add(str(node.value))
# A KEY column is how the transform looks a row UP, so naming it in code is
# correct and expected ("c1_backend_depth" as an output column). What must not
# be duplicated is the PARAMETER the row carries — the weight, threshold or
# verdict the lookup returns. Skip the first column and any *_id/key/name/
# criterion column; check the rest.
KEYISH = ("id", "key", "name", "criterion", "code", "slug", "label")
for pcsv in sorted(Path("data").rglob("*.csv")):
    if not any(h in pcsv.parent.name.lower() for h in POLICY_HINT):
        continue
    import csv as _csv
    with pcsv.open(newline="") as fh:
        prows = list(_csv.DictReader(fh))
    if not prows:
        continue
    cols = list(prows[0])
    for col in cols[1:]:                       # first column is the key
        if any(k in col.lower() for k in KEYISH):
            continue
        for row in prows:
            v = (row[col] or "").strip()
            # Distinctive = long enough to be a real policy value, or a
            # decimal/multi-digit number. Single digits and 1-3 char codes
            # collide with array indices and unrelated strings.
            distinctive = len(v) >= 4 or (
                v.replace(".", "", 1).isdigit() and len(v) >= 2)
            if distinctive and v in tlits:
                derr("policy.literal_duplicates_landed_value",
                    f"{pcsv}: value {v!r} (column '{col}') is landed AND "
                    f"appears as a literal in transform/main.py. The "
                    f"transform must READ it from the row; a copy diverges "
                    f"from the row the user edits.", f"{pcsv}:{col}")

if derrors:
    say("\nPHASE D FAILED — policy boundary (rulings are data, not code):")
    seen = set()
    for (dcode, dat), e in zip(dcodes, derrors):
        if e in seen:
            continue
        seen.add(e)
        say(f"  - {e}")
        diag("s3_closure", dcode, e, path=cpath(dat))
    close_stage("s3_closure", "failed", errors=len(seen))
    finish(1)
close_stage("s3_closure", "passed", scanned=len(scan))
say("phase D ok — rulings land as editable data with status + provenance, "
    "not transform literals")
# FROZEN STRING — do NOT "fix" the stale label. Phase C's MEANING changed with
# this design (it now verifies the byte-copied spec snapshot, the lock and the
# build record, not the completeness of a hand-written context document) but its
# LABEL stays "C (context-completeness)" because run.py's deterministic-check wiring
# and every scenario checker key on this line byte-for-byte. Accuracy of the
# label loses to stability of the contract; this comment is what keeps the
# trade visible instead of inviting a helpful rename that breaks every checker.
say("SELF-CHECK OK — Phases A (structural), B (transform dry-run), "
    "C (context-completeness), D (policy boundary) all passed.")

# Distribution read-back. NOT a gate — it never fails the run. It prints the
# value counts of every classification-shaped string column of every derived
# model, so a fabricated gate or verdict is visible instead of hiding behind a
# green exit. Unconditional by design: deciding which columns "matter" is the
# judgement that would make this unreliable. A column qualifies on shape alone —
# it must actually GROUP (few distinct values, and fewer than one per row), which
# excludes keys and free text without naming either. Relay these counts to the
# user before the build (see nxd-pocket-loop Step 3). It is also the designated
# stage-8 predictor: a green build that answers wrongly shows up here first, so
# it is recorded as DATA in build-record.readback, not only printed.
for m in sorted(set(PHYSICAL_MODELS) - set(BASE_MODELS)):
    n_rows = con.execute(f"SELECT COUNT(*) FROM main.{m}").fetchone()[0]
    cols = [r[0] for r in con.execute(
        f"SELECT name FROM pragma_table_info('{m}') WHERE type = 'VARCHAR'").fetchall()
        if not r[0].startswith("_dlt_")]  # dlt bookkeeping, not model data
    for c in cols:
        rows = con.execute(f'SELECT "{c}", COUNT(*) FROM main.{m} '
                           f'GROUP BY 1 ORDER BY 2 DESC').fetchall()
        if not (len(rows) <= 12 and len(rows) * 2 <= n_rows):
            continue  # a key or free text, not a classification
        counts = ", ".join(f"{v!r}={n}" for v, n in rows)
        uniform = len(rows) == 1
        flag = "  <- UNIFORM: this column does not discriminate" if uniform else ""
        say(f"distribution {m}.{c}: {counts}{flag}")
        values = [{"value": v, "count": n} for v, n in rows]
        READBACK["distribution"].append(
            {"model": m, "column": c, "values": values, "uniform": uniform,
             "origin": "tool_computed"})
        # Evidence keys are the ones dp_diagnostics._merge_readback reads back
        # (model / column / values / uniform). Renaming one here silently
        # empties the build record's readback block.
        diag("s2_transform", "semantic.distribution",
             f"distribution {m}.{c}: {counts}",
             path=cpath(f"transform/main.py:{m}.{c}"),
             evidence={"model": m, "column": c, "values": values,
                       "uniform": uniform})
        if uniform:
            diag("s2_transform", "semantic.uniform_column",
                 f"{m}.{c} has one value across {n_rows} rows — a column built "
                 f"to distinguish rows that does not discriminate. A gate that "
                 f"passes every row is not a gate.",
                 path=cpath(f"transform/main.py:{m}.{c}"),
                 evidence={"model": m, "column": c, "values": values,
                           "uniform": True},
                 fix="State it to the user before the build. Do not silently "
                     "repair it: a gate that cannot fail is a ruling you "
                     "authored, so it lands in nxd_decisions or goes back as a "
                     "question.")

# Declared-but-absent read-back. The dual of UNIFORM, and equally unconditional:
# a vocabulary the closure LANDS (verdict labels, statuses, buckets) whose value
# never appears in any derived column is a branch that did not fire. Deciding
# whether it CANNOT fire needs reasoning and stays with you — this only reports
# what is mechanically true: declared, never produced. Vocabularies come from
# landed data, never from a transform literal, so this is independent of the
# code it is checking.
produced = set()
for m in sorted(set(PHYSICAL_MODELS) - set(BASE_MODELS)):
    for (c,) in con.execute(
            f"SELECT name FROM pragma_table_info('{m}') "
            f"WHERE type = 'VARCHAR'").fetchall():
        if c.startswith("_dlt_"):
            continue
        produced |= {str(v[0]).strip() for v in con.execute(
            f'SELECT DISTINCT "{c}" FROM main.{m}').fetchall() if v[0] is not None}
VOCAB_HINT = ("verdict", "bucket", "outcome", "band", "tier", "category")
for vcsv in sorted(Path("data").rglob("*.csv")):
    # nxd_decisions is the ledger ABOUT the policy, not an output vocabulary:
    # its own status values are meant to describe rulings, not to appear in a
    # scored row. Reporting them absent would be noise on every closure.
    if vcsv.parent.name == "nxd_decisions":
        continue
    import csv as _csv
    with vcsv.open(newline="") as fh:
        vrows = list(_csv.DictReader(fh))
    for col in (vrows[0] if vrows else {}):
        if not any(h in col.lower() for h in VOCAB_HINT):
            continue
        declared = {(r[col] or "").strip() for r in vrows} - {""}
        missing = sorted(d for d in declared if d not in produced)
        if missing and len(declared) <= 12:
            say(f"ABSENT {vcsv.parent.name}.{col}: declared {missing} — "
                f"never produced in any derived column")
            READBACK["absent"].append(
                {"source": vcsv.parent.name, "column": col,
                 "declared_missing": missing, "origin": "tool_computed"})
            diag("s2_transform", "semantic.absent_vocabulary",
                 f"ABSENT {vcsv.parent.name}.{col}: declared {missing} — never "
                 f"produced in any derived column",
                 path=cpath(f"{vcsv}:{col}"),
                 evidence={"source": vcsv.parent.name, "column": col,
                           "declared_missing": missing})

finish(0)
```

The read-back prints **after** `SELF-CHECK OK`, deliberately: it is the last
thing on screen, and it is not what the OK line attests to. Read it before you
report the run — a gate that passed every row, or a verdict that came out
single-valued, is a number you invented, and it is now the last thing you saw
rather than the thing the success banner scrolled past.

## Reading a failure

The row counts printed for derived models are worth reading, not just passing:
a derived table with zero rows, or with exactly as many rows as its source when
the derivation was supposed to expand or collapse, means the derivation ran but
did nothing. The Step-3b asserts should have caught that — if they did not, the
invariant they encode was too weak.

Reading a **Phase B** failure: it executed, so what it reports is what will
happen on the supervisor. There is no kernel and no network in this phase, so a
failure here is never environmental and is never a reason to retry — it is
unambiguously the generated code. A fired assert (`runtime.assert_failed`) is the
transform's own invariant rejecting the data it produced: that is the check
working, not the check being wrong. Fix the derivation, never the assert.

Reading a **Phase C** failure: each one names a specific missing or mismatched
record file, and none of them is fixed by hand-editing the closure.
`dp-spec.approved.md does not match ... snapshot_sha256` means the in-closure
copy of the plan was edited after it was written — the plan a build was compiled
from is not editable in place, so change the live `dp-spec.md`, re-approve, and
regenerate. `compiled_from does not equal ... spec_hash` means the build record
describes a build of a *different* plan than the one snapshotted here; regenerate
rather than reconciling by hand. `spec_status_at_copy` not `approved` is the one
Phase C finding that is not yours to fix: it means the closure was generated from
a spec nobody signed off, and approval is a user act. A missing
`build-record.json` means outcomes have nowhere to land, which would make a green
run indistinguishable from a green run that conceded something — run
`dp_diagnostics.py record init` at generation, before this script.

Reading a **Phase D** failure: it is not a formatting complaint. `nxd_decisions
is promised but is not in BASE_MODELS` means the ledger is generated from a
Python literal, so it documents the code rather than driving it — the row a user
edits has no effect, and the two drift apart the moment either changes. Fix it by
writing `data/nxd_decisions/nxd_decisions.csv` and reading it like any other base
model, never by deleting the model or loosening the check. `value X is landed AND
appears as a literal` means the same value exists in two places that can
disagree: delete the literal and read the row.

`nxd_decisions.csv has no 'provenance' column` means the ledger records whether
each ruling is settled but not who wrote it — so a reviewer cannot separate the
user's weights from the ones you invented. Add the column and classify **every**
row from the fixed set; do not backfill them all as `user_confirmed` to clear the
gate, which is the exact erasure the column exists to prevent. `provenance has
[...]` means a value outside that set: the vocabulary is closed precisely so the
class is queryable, so map your value onto one of the four rather than widening
the set. Which value belongs on which row is in
[derivation-plan.md](derivation-plan.md).

An **ABSENT** line reports a declared value no derived column ever produced. It
is mechanical and says only that: on this data, that branch did not fire. Whether
it *cannot* fire is yours to work out — and if a rule makes a verdict
unreachable (a criterion that can never reach the score its own branch needs),
say so to the user rather than shipping a branch that is dead by construction.

The **distribution read-back** is read the same way, and it is the one the
success banner is most likely to bury. A `UNIFORM` line means a column you built
to distinguish rows does not: a gate that passes every row is not a gate, and a
classification with one value classified nothing. That is a value you supplied,
not one the data produced. Two things follow. **State the distribution to the
user before building** — a uniform gate by name, and what it was supposed to
separate. And do not silently repair it: a gate that cannot fail is a ruling you
authored, so it lands in `nxd_decisions` like any other, or it goes back to the
user as a question. A non-uniform distribution is not a pass either — it is
simply the shape of what you produced, and it is worth one line in the handoff.

Reading a Phase A failure: every message names the file, model, and column. A
kwarg rejection (`join() takes to=, not to_model=`) is a typo — fix the call. A
naming-invariant failure is a diverged name — fix the NAME in every place it
appears (`models.py`, `.promise`, `PHYSICAL_MODELS`, `data/<name>/`), never
quote around it. If a message contradicts the installed wheel's actual
behaviour, the pin has drifted: re-derive that one signature, and update
`nxd-spec-api.md` and this script together.
