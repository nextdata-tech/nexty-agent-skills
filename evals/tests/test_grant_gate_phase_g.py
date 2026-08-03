"""Phase G — the consent gate — must decide BEFORE the transform executes.

``field_mapper/grant.py`` says in its own module docstring that the grant is "a
userland convention, not an enforceable security boundary", and that something
outside it is what fails a closure mapping without a matching grant. For a long
time nothing did: the sentence named an enforcer that did not exist, and a
consent record nobody checks is a file rather than a consent record. Phase G is
that enforcer, and these tests are what keep the sentence true.

**Ordering.** Phase B imports ``transform.main`` and calls ``ingest(...)``. That
is not a dry run for a mapper closure: the harness resolves its API key from
secrets with an environment fallback, so on a machine with ``ANTHROPIC_API_KEY``
set, self-checking a vendored-mapper closure makes live model calls during Phase
B — real disclosure of the closure's source content and real spend. A consent
verdict delivered afterwards is a report about consent already spent, and it
still prints a red banner, so the failure looks like it worked.
``test_phase_g_decides_before_phase_b_imports`` asserts byte offsets in the
shipped script rather than prose about them.

**The trigger.** An import-level root name in ANY module under ``transform/`` —
moving the import into ``transform/helpers.py`` is the same closure mapping the
same content, not an exemption. Two of the
tests below pin closures that PASS or fail in ways a later reader may want to
"fix": ``test_records_only_import_still_requires_grant`` (a resolve-only closure
still needs consent, because the proposals it re-lands are model-derived data)
and ``test_closure_without_mapper_emits_nothing`` (the gate is inert for the
approximately-all closures that never vendor the harness — a gate that fires on
those gets deleted rather than obeyed). Both are deliberate.

**What is NOT pinned, because it is not covered.** A closure that renames the
vendor directory, reaches the package through ``importlib``, or pastes
``transport.py``'s body inline never fires this gate — and passes Phase E too,
since the mapper's ``import anthropic`` is function-local inside the package and
invisible to an AST walk over the transform. The pair of gates catches the
closure that drifted, never the one that lied.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EVALS_DIR.parent
SELF_CHECK = REPO_ROOT / "src" / "nxd-run-job-loop" / "scripts" / "self_check.py"
REAL_MAPPER = REPO_ROOT / "src" / "nxd-generate-data-product" / "mapper" / "field_mapper"
REAL_SAMPLE = REPO_ROOT / "src" / "nxd-generate-data-product" / "mapper" / "samples" / "01-row-scores"

CSV = '_csv = "/infra-profile/desktop-local#/services/csv-source"\n'

CLEAN_TRANSFORM = (
    "import dlt\n"
    "from nxd import data_product\n"
)

MAPPER_TRANSFORM = (
    "import dlt\n"
    "from field_mapper import map_inputs\n"
    "from nxd import data_product\n"
    "def go():\n"
    "    return map_inputs([], spec=None, grant=None, run_dir='', call=None)\n"
)


def _script_body() -> str:
    """The shipped ``self_check.py`` source the agent copies into the closure."""
    return SELF_CHECK.read_text(encoding="utf-8")


def _phase_g_source() -> str:
    """Phase G's block, sliced on its explicit anchors.

    Anchors rather than a content heuristic, for the reason recorded beside the
    Phase D slice in the script itself: a slice keyed on surrounding prose rots
    the moment anything is inserted next to it, and it rots SILENTLY — an empty
    or truncated block still "passes" every assertion that only checks for the
    absence of a finding.
    """
    body = _script_body()
    start = body.index("# === PHASE-G-BEGIN ===")
    end = body.index("# === PHASE-G-END ===")
    return body[start:end]


def _run_phase_g(
    closure: Path,
    *,
    expect_exit: int,
    transform_src: str = MAPPER_TRANSFORM,
    spec_src: str = CSV,
) -> str:
    """Execute Phase G standalone against a synthetic closure on disk.

    Unlike the Phase E harness this one needs a real directory: Phase G walks
    ``contracts/`` for JSON, and subprocesses ``python -m field_mapper`` with the
    closure as cwd, so the vendored package has to actually be there.

    ``expect_exit`` is mandatory for Phase E's reason. The banner text and the
    exit code are independent — printing "PHASE G FAILED" is what a reader sees,
    but ``sys.exit(1)`` is what stops the run before Phase B imports the
    transform and spends money under a grant that does not authorize it.
    """
    harness = (
        "import ast, json, re, sys\n"
        "from pathlib import Path\n"
        "DIAGS = []\n"
        "def say(*a, **k): print(*a, **k)\n"
        "def cpath(at): return f'closure:{at}' if at else ''\n"
        "def diag(stage, code, message, *, path='', evidence=None, fix=None):\n"
        "    DIAGS.append({'stage': stage, 'code': code, 'path': path})\n"
        "def close_stage(stage, state, **detail): pass\n"
        "def _dump(): print('DIAGS_JSON=' + json.dumps(DIAGS))\n"
        "def finish(code):\n"
        "    _dump()\n"
        "    sys.exit(code)\n"
        # Phase G consumes three names defined in Phase E's block. Re-stated
        # here rather than splicing Phase E in: this file is testing the consent
        # gate, and dragging in the reach gate's spec-parsing would make a Phase
        # E regression show up as a Phase G failure.
        "def imported_roots(src, path):\n"
        "    out = set()\n"
        "    for node in ast.walk(ast.parse(src, path)):\n"
        "        if isinstance(node, ast.Import):\n"
        "            out |= {a.name for a in node.names}\n"
        "        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:\n"
        "            out.add(node.module)\n"
        "            out |= {f'{node.module}.{a.name}' for a in node.names}\n"
        "    return out\n"
        "def denied_hit(mod, roots):\n"
        "    return next((r for r in roots\n"
        "                 if mod == r or mod.startswith(r + '.')), None)\n"
        f"transform_src = {transform_src!r}\n"
        f"spec_src = {spec_src!r}\n"
        "t_imports = imported_roots(transform_src, 'transform/main.py')\n"
    ) + _phase_g_source() + "\n_dump()\n"
    (closure / "contracts").mkdir(parents=True, exist_ok=True)
    script = closure / "_phase_g.py"
    script.write_text(harness, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script)], cwd=closure, capture_output=True, text=True
    )
    out = proc.stdout + proc.stderr
    assert "Traceback" not in out, (
        "Phase G let an exception escape. A broken vendored package, an "
        f"unreadable grant or a failed subprocess must arrive as a FINDING — a "
        f"traceback takes every other phase's verdict down with it.\n{out}"
    )
    assert proc.returncode == expect_exit, (
        f"expected exit {expect_exit}, got {proc.returncode}. A deny must exit 1 "
        f"(the run stops before Phase B executes the transform and spends under "
        f"a grant that does not authorize it); an allow must exit 0.\n{out}"
    )
    return out


def _diags(out: str) -> list[dict]:
    line = next((ln for ln in out.splitlines() if ln.startswith("DIAGS_JSON=")), None)
    assert line is not None, f"harness emitted no diagnostics dump:\n{out}"
    return json.loads(line[len("DIAGS_JSON="):])


def _codes(out: str) -> list[str]:
    return [d["code"] for d in _diags(out)]


def _vendor(closure: Path) -> None:
    """Copy the REAL harness in. The subprocess oracle is the thing under test."""
    shutil.copytree(REAL_MAPPER, closure / "field_mapper")
    (closure / "contracts").mkdir(parents=True, exist_ok=True)


def _spec(closure: Path) -> None:
    """Put a real, hashable mapper spec under contracts/."""
    (closure / "contracts").mkdir(parents=True, exist_ok=True)
    shutil.copy(REAL_SAMPLE / "spec.json", closure / "contracts" / "spec.json")


def _real_spec_id(closure: Path) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "field_mapper", "spec-id", "contracts/spec.json"],
        cwd=closure, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["mapper_spec_id"]


def _grant_doc(spec_id: str, **over) -> dict:
    doc = json.loads((REAL_SAMPLE / "grant.json").read_text())
    doc["mapper_spec_id"] = spec_id
    doc.update(over)
    return doc


def _write(closure: Path, rel: str, doc: dict) -> None:
    p = closure / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2), encoding="utf-8")


# --------------------------------------------------------------- ordering ---

def test_phase_g_decides_before_phase_b_imports():
    """The gate's exit must precede the execution it is gating.

    For a mapper closure Phase B is not a dry run in any meaningful sense: it
    imports and calls the transform, which resolves a key and calls a model. A
    consent check placed after it reports on disclosure that already happened.
    """
    body = _script_body()
    gate_exit = body.index("PHASE G FAILED")
    # Anchored at line starts: both this phase's own comments and Phase E's
    # mention `sys.path.insert(0, ".")` in prose ABOVE the statement, and a
    # substring search would happily match the commentary and pass while the
    # gate sat below the real import.
    for later in ('\nsys.path.insert(0, ".")',
                  "\n    from transform.main import",
                  "\n    ingest(duckdb=out"):
        assert gate_exit < body.index(later), (
            f"Phase G's failure exit must come before {later!r}. Below it, the "
            f"transform has already run under an unauthorized grant."
        )


def test_phase_g_sits_after_phase_e_ok():
    """G runs after E: it reuses E's helpers and is strictly more privileged."""
    body = _script_body()
    assert body.index("phase E ok") < body.index("=== PHASE-G-BEGIN ==="), (
        "Phase G must follow Phase E. It consumes imported_roots/denied_hit/"
        "t_imports from E's block, and E is purely static where G subprocesses "
        "vendored code — the more privileged phase runs later."
    )


def test_phase_g_block_is_not_empty():
    """The anchors must actually enclose the gate.

    A slice that silently returns nothing makes every 'no finding' assertion in
    this file pass while testing an empty string.
    """
    src = _phase_g_source()
    assert "grant.missing" in src and "PHASE G FAILED" in src, src[:400]


# ------------------------------------------------------------ inert case ---

def test_closure_without_mapper_emits_nothing(tmp_path):
    """The ~all closures that never vendor the harness must be untouched.

    A gate that fires on closures with no mapper is a gate that gets deleted
    rather than obeyed, and it would take every unrelated closure down with it.
    """
    out = _run_phase_g(tmp_path, expect_exit=0, transform_src=CLEAN_TRANSFORM)
    assert [c for c in _codes(out) if c.startswith("grant.")] == []
    assert "phase G ok" in out
    assert "no consent obligation" in out


# --------------------------------------------------------- consent missing ---

def test_vendored_mapper_without_grant_fails(tmp_path):
    """THE test: this is what makes grant.py's docstring sentence true.

    A closure that vendors the harness, carries a spec, and has no grant used to
    self-check green. Consent was documented, never required.
    """
    _vendor(tmp_path)
    _spec(tmp_path)
    out = _run_phase_g(tmp_path, expect_exit=1)
    assert _codes(out) == ["grant.missing"], _codes(out)
    assert "no consent grant" in out


def test_records_only_import_still_requires_grant(tmp_path):
    """A resolve-only closure still needs consent. Deliberate, so pinned.

    It makes no model call — it re-lands wide rows from proposals and reviews
    that already exist. But those proposals are model-derived data, and the
    consent record travels with the data it authorized. Narrowing the trigger to
    "importers of map_inputs" would also reopen the transport-direct bypass.
    """
    _vendor(tmp_path)
    _spec(tmp_path)
    out = _run_phase_g(
        tmp_path, expect_exit=1,
        transform_src=("from field_mapper.records import reviews_from_csv\n"
                       "map_inputs = None\n"),
    )
    assert "grant.missing" in _codes(out), _codes(out)


def test_spec_absent_is_a_finding(tmp_path):
    """A spec inlined as a Python literal has no stable id to consent to."""
    _vendor(tmp_path)
    out = _run_phase_g(tmp_path, expect_exit=1)
    assert _codes(out) == ["grant.spec_unreadable"], _codes(out)


# ------------------------------------------------------------ binding ---

def test_matching_grant_passes(tmp_path):
    """The only end-to-end proof the subprocess oracle works.

    A gate that can only fail is indistinguishable from a gate that is broken,
    and every other test here would still pass if `spec-id` returned garbage.
    """
    _vendor(tmp_path)
    _spec(tmp_path)
    spec_id = _real_spec_id(tmp_path)
    _write(tmp_path, "contracts/grant.json", _grant_doc(spec_id))
    out = _run_phase_g(tmp_path, expect_exit=0)
    assert [c for c in _codes(out) if c.startswith("grant.")] == [], _codes(out)
    assert "phase G ok" in out
    assert "1 mapper spec(s) under contracts/" in out


def test_grant_bound_to_wrong_hash_fails(tmp_path):
    """A well-formed grant for a different spec authorizes nothing.

    The defect this pins is a name-bound or vacuous comparison — exactly what
    Grant's class docstring warns a name-bound grant would be: it would silently
    authorize an instruction the user never saw.
    """
    _vendor(tmp_path)
    _spec(tmp_path)
    _write(tmp_path, "contracts/grant.json", _grant_doc("0" * 32))
    out = _run_phase_g(tmp_path, expect_exit=1)
    assert _codes(out) == ["grant.spec_mismatch"], _codes(out)


def test_placeholder_derived_id_is_invalid(tmp_path):
    """`<derived>` is the samples-only escape hatch; in a closure it is a wildcard.

    The fixture loader substitutes it with whatever spec it is handed. Leaked
    into a closure, a grant carrying it authorizes anything.
    """
    _vendor(tmp_path)
    _spec(tmp_path)
    _write(tmp_path, "contracts/grant.json", _grant_doc("<derived>"))
    out = _run_phase_g(tmp_path, expect_exit=1)
    assert _codes(out) == ["grant.invalid"], _codes(out)
    assert "<derived>" in out


def test_expired_grant_fails(tmp_path):
    """Consent lapses. A closure green yesterday failing today is the point."""
    _vendor(tmp_path)
    _spec(tmp_path)
    spec_id = _real_spec_id(tmp_path)
    _write(tmp_path, "contracts/grant.json",
           _grant_doc(spec_id, expires_at="2001-01-01T00:00:00Z"))
    out = _run_phase_g(tmp_path, expect_exit=1)
    assert _codes(out) == ["grant.expired"], _codes(out)


def test_grant_naming_a_different_model_fails(tmp_path):
    """Consent is PER MODEL — a second model is a separate disclosure."""
    _vendor(tmp_path)
    _spec(tmp_path)
    spec_id = _real_spec_id(tmp_path)
    _write(tmp_path, "contracts/grant.json",
           _grant_doc(spec_id, model="some-other-model"))
    out = _run_phase_g(tmp_path, expect_exit=1)
    assert _codes(out) == ["grant.spec_mismatch"], _codes(out)


def test_stray_grant_warns_and_passes(tmp_path):
    """Stale consent is a warning, not an error.

    It authorizes nothing and fails nothing — but left on disk it is what a
    later reader mistakes for coverage. Misclassified as an error it would fail
    compliant closures; dropped entirely it would be invisible.
    """
    _vendor(tmp_path)
    _spec(tmp_path)
    spec_id = _real_spec_id(tmp_path)
    _write(tmp_path, "contracts/grant.json", _grant_doc(spec_id))
    _write(tmp_path, "contracts/stale.json", _grant_doc("a" * 32))
    out = _run_phase_g(tmp_path, expect_exit=0)
    assert _codes(out) == ["grant.unbound"], _codes(out)
    assert "phase G ok" in out


# ------------------------------------------------------------- bypasses ---

def test_helper_module_import_triggers_the_gate(tmp_path):
    """The honest refactor: the mapper import lives in transform/helpers.py.

    A gate that reads only transform/main.py sees a clean import list and lets
    Phase B execute the mapping. Nothing about moving an import into a sibling
    module changes what the closure discloses, so the trigger is every module
    under transform/, not one file.
    """
    _vendor(tmp_path)
    _spec(tmp_path)
    (tmp_path / "transform").mkdir(parents=True, exist_ok=True)
    (tmp_path / "transform" / "helpers.py").write_text(
        "from field_mapper import map_inputs\n"
        "def run():\n"
        "    return map_inputs([], spec=None, grant=None, run_dir='', call=None)\n",
        encoding="utf-8")
    out = _run_phase_g(tmp_path, expect_exit=1,
                       transform_src="from transform.helpers import run\n")
    assert "grant.missing" in _codes(out), _codes(out)
    assert "transform/helpers.py" in out, out


def test_helper_module_with_matching_grant_passes(tmp_path):
    """The same closure, consented. Proves the widened scan is not one-sided.

    It also proves the widened `map_inputs` reference scan reads helpers.py: if
    it still looked only at main.py it would see no `map_inputs` and raise
    grant.ungated_map on a closure whose helper calls exactly that.
    """
    _vendor(tmp_path)
    _spec(tmp_path)
    (tmp_path / "transform").mkdir(parents=True, exist_ok=True)
    (tmp_path / "transform" / "helpers.py").write_text(
        "from field_mapper import map_inputs\n"
        "def run():\n"
        "    return map_inputs([], spec=None, grant=None, run_dir='', call=None)\n",
        encoding="utf-8")
    spec_id = _real_spec_id(tmp_path)
    _write(tmp_path, "contracts/grant.json", _grant_doc(spec_id))
    out = _run_phase_g(tmp_path, expect_exit=0,
                       transform_src="from transform.helpers import run\n")
    assert [c for c in _codes(out) if c.startswith("grant.")] == [], _codes(out)
    assert "phase G ok" in out


def test_aliased_map_inputs_import_is_not_ungated(tmp_path):
    """`from field_mapper import map_inputs as mi` still routes through consent.

    The reference scan looks for the name `map_inputs`; under an alias that name
    never appears, so a purely textual check calls a consented closure ungated.
    An import alias is recorded in the AST — read it rather than guess.
    """
    _vendor(tmp_path)
    _spec(tmp_path)
    spec_id = _real_spec_id(tmp_path)
    _write(tmp_path, "contracts/grant.json", _grant_doc(spec_id))
    out = _run_phase_g(
        tmp_path, expect_exit=0,
        transform_src=("from field_mapper import map_inputs as mi\n"
                       "def go():\n"
                       "    return mi([], spec=None, grant=None, run_dir='', call=None)\n"))
    assert "grant.ungated_map" not in _codes(out), _codes(out)
    assert "phase G ok" in out


def test_transport_direct_without_map_inputs_fails(tmp_path):
    """The bypass grant.py names in its own docstring.

    `transport.Client` takes no grant. `map_inputs` is the only entry point
    where `Grant.check` runs, and its `grant` parameter is required — so a
    transform that imports the package and never mentions `map_inputs` routed
    around the consent path entirely.
    """
    _vendor(tmp_path)
    _spec(tmp_path)
    spec_id = _real_spec_id(tmp_path)
    _write(tmp_path, "contracts/grant.json", _grant_doc(spec_id))
    out = _run_phase_g(
        tmp_path, expect_exit=1,
        transform_src="from field_mapper.transport import Client\n",
    )
    assert "grant.ungated_map" in _codes(out), _codes(out)


def test_verifier_importing_field_mapper_is_denied(tmp_path):
    """Verifier-side mapping is invisible to Phase E and never grant-waivable.

    Phase E scans verifiers for MODEL_ROOTS only, and the mapper reaches a model
    through a function-local `import anthropic` inside its own package — so a
    verifier that maps passes Phase E while doing precisely what Phase E's own
    message forbids: re-deciding pass/fail on every run.
    """
    (tmp_path / "contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "contracts" / "x.py").write_text(
        "import field_mapper\ndef check(df): return True\n", encoding="utf-8")
    out = _run_phase_g(tmp_path, expect_exit=1, transform_src=CLEAN_TRANSFORM)
    assert _codes(out) == ["grant.verifier_maps"], _codes(out)
    assert "contracts/x.py" in out


def test_broken_vendored_package_is_a_finding_not_a_traceback(tmp_path):
    """A subprocess failure must not take the whole self-check with it."""
    _vendor(tmp_path)
    (tmp_path / "field_mapper" / "__init__.py").write_text(
        "raise RuntimeError('gutted')\n", encoding="utf-8")
    _spec(tmp_path)
    # A well-formed grant is present so the failure cannot be confused with
    # `grant.missing`: the ONLY thing wrong here is that the vendored package
    # cannot answer for its own spec.
    _write(tmp_path, "contracts/grant.json", _grant_doc("b" * 32))
    out = _run_phase_g(tmp_path, expect_exit=1)
    assert "grant.spec_unreadable" in _codes(out), _codes(out)
    # And the finding must READ like a finding — the subprocess's own traceback
    # must not be pasted into a report where "Traceback" means the tool crashed.
    assert "runpy" not in out


# ------------------------------------------------------------- registries ---

def test_grant_codes_are_registered_in_the_shared_vocabulary():
    """Every code Phase G emits must exist in dp_diagnostics' registry."""
    sys.path.insert(0, str(REPO_ROOT / "src" / "nxd-run-job-loop" / "scripts"))
    import dp_diagnostics as dpd

    emitted = set(re.findall(r'"(grant\.[a-z_]+)"', _phase_g_source()))
    assert emitted, "Phase G emits no grant.* codes — the slice is wrong"
    for code in sorted(emitted):
        assert code in dpd.CODES, f"{code} is emitted but unregistered"
        assert dpd.CODES[code]["stage"] == "s1_structure", code

    user_owned = {"grant.missing", "grant.spec_mismatch", "grant.expired"}
    for code in sorted(emitted):
        want = "user" if code in user_owned else "agent"
        assert dpd.CODES[code]["owner"] == want, (
            f"{code} should be owner:{want} — consent is the user's act, "
            f"closure defects are the agent's"
        )


def test_grant_codes_are_registered_in_the_scripts_own_table():
    """The KeyError that the stubbed harness above structurally cannot catch.

    `diag()` looks the code up in the script's inlined CODES table and raises
    KeyError on a miss, killing the entire self-check on exactly the runs this
    gate exists for. Every test above stubs `diag`, so none of them would notice.
    """
    body = _script_body()
    table = body[:body.index("JSON_MODE =")]
    for code in sorted(set(re.findall(r'"(grant\.[a-z_]+)"', _phase_g_source()))):
        assert f'"{code}"' in table, (
            f"{code} is emitted by Phase G but absent from self_check.py's own "
            f"CODES table — diag() will raise KeyError and take the whole "
            f"self-check with it"
        )


def test_phase_g_failure_reports_through_the_real_diagnostic_surface(tmp_path):
    """Drive the failure through the SHIPPED preamble, not the stub harness.

    Same bug class as the test above, on the real surface: the stubs cannot see
    a KeyError inside the genuine `diag`, so this splices the actual CODES table
    and diagnostic plumbing in front of the phase.
    """
    body = _script_body()
    preamble = body[:body.index("JSON_MODE =")]
    harness = (
        preamble
        + "\nJSON_MODE = False\nDIAGS = []\n"
          "STAGE_STATE = {'s1_structure': None, 's2_transform': None,\n"
          "               's3_closure': None}\n"
          "STAGE_AT, STAGE_DETAIL = {}, {}\n"
          "def say(*a, **k): print(*a, **k)\n"
          "def cpath(at): return f'closure:{at}' if at else ''\n"
          "def diag(stage, code, message, *, path='', evidence=None, fix=None):\n"
          "    sev, owner = CODES[code]\n"
          "    DIAGS.append({'stage': stage, 'code': code, 'severity': sev,\n"
          "                  'owner': owner})\n"
          "def close_stage(stage, state, **detail): pass\n"
          "def _dump(): print('DIAGS_JSON=' + json.dumps(DIAGS))\n"
          "def finish(code):\n"
          "    _dump()\n"
          "    sys.exit(code)\n"
          "def imported_roots(src, path):\n"
          "    out = set()\n"
          "    for node in ast.walk(ast.parse(src, path)):\n"
          "        if isinstance(node, ast.Import):\n"
          "            out |= {a.name for a in node.names}\n"
          "        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:\n"
          "            out.add(node.module)\n"
          "            out |= {f'{node.module}.{a.name}' for a in node.names}\n"
          "    return out\n"
          "def denied_hit(mod, roots):\n"
          "    return next((r for r in roots\n"
          "                 if mod == r or mod.startswith(r + '.')), None)\n"
        + f"transform_src = {MAPPER_TRANSFORM!r}\n"
        + f"spec_src = {CSV!r}\n"
          "t_imports = imported_roots(transform_src, 'transform/main.py')\n"
        + _phase_g_source() + "\n_dump()\n"
    )
    _vendor(tmp_path)
    (tmp_path / "contracts").mkdir(parents=True, exist_ok=True)
    _spec(tmp_path)
    script = tmp_path / "_real.py"
    script.write_text(harness, encoding="utf-8")
    proc = subprocess.run([sys.executable, str(script)], cwd=tmp_path,
                          capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    assert "KeyError" not in out, out
    assert "Traceback" not in out, out
    assert proc.returncode == 1, out
    codes = [d["code"] for d in _diags(out)]
    assert codes == ["grant.missing"], codes
    assert _diags(out)[0]["owner"] == "user"


def test_gate_agrees_with_grant_py_on_malformed_grants(tmp_path):
    """The inlined shape checks must not drift from grant.py's own rules.

    Two copies of a consent rule is how a gate ends up enforcing something other
    than what it claims. Phase G calls the harness rather than reimplementing
    it, and this asserts the two verdicts agree on grants the harness rejects.
    """
    sys.path.insert(0, str(REPO_ROOT / "src" / "nxd-generate-data-product" / "mapper"))
    from field_mapper.errors import GrantError, SpecError
    from field_mapper.grant import Grant

    _vendor(tmp_path)
    _spec(tmp_path)
    spec_id = _real_spec_id(tmp_path)

    # The last two OMIT a required key rather than carrying a bad value, which
    # is the case that broke: recognition used to require the full key set, so a
    # grant missing one was not recognised as a grant at all. The gate then
    # reported grant.missing — owner: user, next_action: confirm — telling the
    # human to re-consent to a rubric they had already consented to, while the
    # grant sat in contracts/. A value-only fixture cannot catch that, because
    # every one of its docs still has all four keys.
    malformed = [
        _grant_doc(spec_id, pii_category="not-a-category"),
        _grant_doc(spec_id, purpose=""),
        {k: v for k, v in _grant_doc(spec_id).items() if k != "purpose"},
        {k: v for k, v in _grant_doc(spec_id).items() if k != "provider"},
    ]
    for doc in malformed:
        try:
            Grant.from_dict(doc)
            harness_rejects = False
        except (GrantError, SpecError):
            harness_rejects = True
        assert harness_rejects, f"harness accepted {doc!r}; update this case"

        _write(tmp_path, "contracts/grant.json", doc)
        out = _run_phase_g(tmp_path, expect_exit=1)
        codes = _codes(out)
        assert "grant.invalid" in codes, (
            f"grant.py rejects {doc!r} but Phase G did not: {codes}"
        )
        # A defective grant is the agent's to repair. Reporting grant.missing
        # here would stop the loop for a human decision over a schema typo, and
        # would state something the closure contradicts.
        assert "grant.missing" not in codes, (
            f"a defective grant was reported as absent for {doc!r}: {codes}"
        )
        assert "carries no consent grant" not in out, (
            f"the report claims no grant exists while one is on disk: {doc!r}"
        )
