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

import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from _harness import harness_path, requires_harness

EVALS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EVALS_DIR.parent
SELF_CHECK = REPO_ROOT / "src" / "nxd-run-job-loop" / "scripts" / "self_check.py"
# The harness lives in the nxd monorepo; only the fixtures are carried here.
# `harness_path()` is None when that checkout is unreachable, which is what
# `requires_harness` skips on — so this stays a module-level lookup rather than
# an import that would error at collection.
REAL_MAPPER = harness_path()
REAL_SAMPLE = REPO_ROOT / "src" / "nxd-generate-data-product" / "mapper" / "samples" / "01-row-scores"

CSV = '_csv = "/infra-profile/desktop-local#/services/csv-source"\n'

CLEAN_TRANSFORM = (
    "import dlt\n"
    "from nxd import data_product\n"
)

MAPPER_TRANSFORM = (
    "import dlt\n"
    "from nxd.experimental.field_mapper import map_inputs\n"
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
    ``contracts/`` for JSON, and subprocesses ``python -m nxd.experimental.field_mapper`` with the
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


def _stand_in(dest: Path) -> None:
    """A harness that HASHES but never JUDGES, for when the monorepo is absent.

    The gate reaches the harness through exactly two verbs — ``spec-id`` and
    ``grant-check`` — and most of the suite only needs the first to be a stable
    function of the spec. That is a hash, not a consent rule, so reproducing it
    here costs nothing and drifts from nothing.

    ``grant-check`` is the line this must not cross. Its real verdicts encode
    consent policy — expiry, model agreement, the wording that Phase G maps to
    ``grant.expired`` (owner: user) versus ``grant.invalid`` (owner: agent) —
    and a second copy of a consent rule is the exact defect the gate exists to
    prevent. So it returns "no problems" unconditionally: enough for tests that
    assert on the gate's own pairing, hash-comparison and reporting logic, and
    useless for tests that assert on a verdict. Those carry
    ``requires_harness`` and run against the real package.
    """
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "__init__.py").write_text("", encoding="utf-8")
    (dest / "__main__.py").write_text(
        "import hashlib, json, sys\n"
        "cmd = sys.argv[1] if len(sys.argv) > 1 else ''\n"
        "if cmd == 'spec-id':\n"
        # Hash the spec's canonical JSON, so the id is stable across calls and
        # different for different specs — the only two properties the gate's
        # pairing logic actually reads. The real harness stamps a wire schema
        # and harness version in first, so this value is deliberately NOT
        # equal to a real spec id; nothing here compares the two.
        "    raw = json.load(open(sys.argv[2], encoding='utf-8'))\n"
        "    blob = json.dumps(raw, sort_keys=True, separators=(',', ':'))\n"
        "    digest = hashlib.sha256(blob.encode()).hexdigest()[:32]\n"
        "    print(json.dumps({'mapper_spec_id': digest}))\n"
        "elif cmd == 'grant-check':\n"
        "    print(json.dumps({'problems': []}))\n"
        "else:\n"
        "    sys.exit(2)\n",
        encoding="utf-8")


def _vendor(closure: Path) -> None:
    """Stage the REAL harness where `nxd.experimental.field_mapper` resolves.

    The harness ships inside the installed ``nxd`` package, so the import the
    gate triggers on is a dotted package path, not a closure-root directory.
    Laying the tree down under the closure — which is the subprocess cwd — makes
    ``python -m nxd.experimental.field_mapper`` resolve exactly as it will from
    site-packages, without requiring the monorepo wheel to be installed in the
    test environment. The subprocess oracle is the thing under test, so it has
    to be the real package rather than a stub.

    When the monorepo is unreachable this falls back to ``_stand_in``, which
    hashes but does not judge — enough for the tests that assert on the gate's
    own logic, and deliberately useless for the ones that assert on a consent
    verdict. Those carry ``requires_harness`` and skip instead.
    """
    pkg = closure / "nxd" / "experimental"
    pkg.mkdir(parents=True, exist_ok=True)
    (closure / "nxd" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    if REAL_MAPPER is not None:
        shutil.copytree(REAL_MAPPER, pkg / "field_mapper")
    else:
        _stand_in(pkg / "field_mapper")
    (closure / "contracts").mkdir(parents=True, exist_ok=True)


def _spec(closure: Path) -> None:
    """Put a real, hashable mapper spec under contracts/."""
    (closure / "contracts").mkdir(parents=True, exist_ok=True)
    shutil.copy(REAL_SAMPLE / "spec.json", closure / "contracts" / "spec.json")


def _real_spec_id(closure: Path) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "nxd.experimental.field_mapper", "spec-id", "contracts/spec.json"],
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
        transform_src=("from nxd.experimental.field_mapper.records import reviews_from_csv\n"
                       "map_inputs = None\n"),
    )
    assert "grant.missing" in _codes(out), _codes(out)


def test_spec_absent_is_a_finding(tmp_path):
    """A spec inlined as a Python literal has no stable id to consent to."""
    _vendor(tmp_path)
    out = _run_phase_g(tmp_path, expect_exit=1)
    assert _codes(out) == ["grant.spec_unreadable"], _codes(out)


# ------------------------------------------------------------ binding ---

@requires_harness
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


@requires_harness
def test_expired_grant_fails(tmp_path):
    """Consent lapses. A closure green yesterday failing today is the point."""
    _vendor(tmp_path)
    _spec(tmp_path)
    spec_id = _real_spec_id(tmp_path)
    _write(tmp_path, "contracts/grant.json",
           _grant_doc(spec_id, expires_at="2001-01-01T00:00:00Z"))
    out = _run_phase_g(tmp_path, expect_exit=1)
    assert _codes(out) == ["grant.expired"], _codes(out)


@requires_harness
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
        "from nxd.experimental.field_mapper import map_inputs\n"
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
        "from nxd.experimental.field_mapper import map_inputs\n"
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
        transform_src=("from nxd.experimental.field_mapper import map_inputs as mi\n"
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
        transform_src="from nxd.experimental.field_mapper.transport import Client\n",
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
        "import nxd.experimental.field_mapper\ndef check(df): return True\n", encoding="utf-8")
    out = _run_phase_g(tmp_path, expect_exit=1, transform_src=CLEAN_TRANSFORM)
    assert _codes(out) == ["grant.verifier_maps"], _codes(out)
    assert "contracts/x.py" in out


def test_verifier_importing_the_legacy_vendored_name_is_denied(tmp_path):
    """The retired spelling must not become an exemption inside contracts/.

    The legacy denial walks `t_modules` — transform/ plus a non-recursive
    closure root — and contracts/ is in neither, so this case reaches the gate
    only through the verifier loop. Before the harness moved into the package
    `MAPPER_ROOT` was "field_mapper" and that loop caught it; matching the
    dotted path alone would retire the coverage along with the spelling and
    leave a verifier free to map against a live model on every run with both
    gates green.
    """
    (tmp_path / "contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "contracts" / "x.py").write_text(
        "import field_mapper\ndef check(df): return True\n", encoding="utf-8")
    out = _run_phase_g(tmp_path, expect_exit=1, transform_src=CLEAN_TRANSFORM)
    assert _codes(out) == ["grant.verifier_maps"], _codes(out)
    # The finding must name what was actually imported, not the constant: a
    # legacy hit reported as `nxd.experimental.field_mapper` sends the reader
    # looking for an import their verifier does not contain.
    assert "'field_mapper'" in out, out


def test_broken_harness_package_is_a_finding_not_a_traceback(tmp_path):
    """A subprocess failure must not take the whole self-check with it."""
    _vendor(tmp_path)
    (tmp_path / "nxd" / "experimental" / "field_mapper" / "__init__.py").write_text(
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


@requires_harness
def test_gate_agrees_with_grant_py_on_malformed_grants(tmp_path):
    """The inlined shape checks must not drift from grant.py's own rules.

    Two copies of a consent rule is how a gate ends up enforcing something other
    than what it claims. Phase G calls the harness rather than reimplementing
    it, and this asserts the two verdicts agree on grants the harness rejects.

    This is the one test that reads the harness as a LIBRARY rather than
    driving it as a subprocess, and it is the reason the gate suite cannot fall
    back to a stub: the rules it compares against are `grant.py`'s own.
    """
    # Imported off the package's parent rather than as
    # `nxd.experimental.field_mapper`: the two modules under test read consent
    # rules that do not depend on where the package is mounted, and importing
    # the dotted path would need the whole `nxd` package on sys.path. The
    # GATE's agreement with them is what is being asserted, and the gate
    # reaches the harness by subprocess, not by this import.
    assert REAL_MAPPER is not None  # guaranteed by @requires_harness
    sys.path.insert(0, str(REAL_MAPPER.parent))
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


# ------------------------------------------------------- the trigger itself ---

# The gate's whole narrowing claim lives in one constant and one prefix rule.
# Before the harness moved into the nxd package, `MAPPER_ROOT` was a globally
# unique root name; now it is a dotted path underneath `nxd`, which is the ONE
# package every closure imports. That makes the boundary rule load-bearing in a
# way it was not before: a truncated MAPPER_ROOT, or a `denied_hit` that stopped
# matching on dot boundaries, would demand a consent grant from every closure in
# existence — and every test above would stay green, because they all vendor a
# real mapper import and assert the gate FIRES.
#
# These cases were checked by hand when the trigger moved. Checking by hand is
# what this test exists to stop being necessary.
TRIGGER_CASES = [
    # (import statement, must the gate fire?)
    ("import nxd.experimental.field_mapper", True),
    ("from nxd.experimental.field_mapper import map_inputs", True),
    ("from nxd.experimental.field_mapper.records import reviews_from_csv", True),
    # Imports the package without naming it in the module path.
    ("from nxd.experimental import field_mapper", True),
    # Every closure carries these. If any of them fires, every build breaks.
    ("import nxd", False),
    ("from nxd import data_product", False),
    ("from nxd.spec import data_product", False),
    # A sibling under the same parent must not be collateral.
    ("from nxd.experimental import semantic", False),
    ("import nxd.experimental.semantic", False),
    # Prefix-but-not-on-a-dot-boundary.
    ("import nxd.experimental.field_mapper_utils", False),
    # The pre-move vendored form. `False` here means it does not match
    # MAPPER_ROOT — which is correct and must stay correct, since the two roots
    # are deliberately separate checks. It does NOT mean the closure passes:
    # `LEGACY_MAPPER_ROOT` denies this spelling by name as
    # `grant.vendored_harness`, covered by
    # `test_the_legacy_vendored_import_is_denied_by_name` below. Were it folded
    # into MAPPER_ROOT instead, a vendored copy would be routed through the
    # grant oracle — offering consent for a harness that answers for its own
    # spec hash, which is exactly what must not be consentable.
    ("import field_mapper", False),
    ("from field_mapper import map_inputs", False),
]


def _trigger_fires(statement: str) -> bool:
    """Run the SHIPPED helpers over one import statement.

    Executes `imported_roots` / `denied_hit` out of the real script rather than
    reimplementing them: a copy of the boundary rule here could agree with
    itself while disagreeing with the gate.
    """
    body = _script_body()
    ns: dict = {"ast": ast}
    for node in ast.parse(body).body:
        if isinstance(node, ast.FunctionDef) and node.name in {
            "imported_roots",
            "denied_hit",
        }:
            exec(compile(ast.Module([node], []), "<self_check>", "exec"), ns)
    root = re.search(r'^MAPPER_ROOT = "([^"]+)"', body, re.M)
    assert root, "MAPPER_ROOT is not a literal assignment in the shipped script"
    roots = ns["imported_roots"](statement, "transform/main.py")
    return any(ns["denied_hit"](m, {root.group(1)}) for m in roots)


@pytest.mark.parametrize("statement,should_fire", TRIGGER_CASES)
def test_trigger_fires_on_the_mapper_and_nothing_else(statement, should_fire):
    fired = _trigger_fires(statement)
    if should_fire:
        assert fired, (
            f"{statement!r} reaches the mapper but does not fire the consent "
            f"gate — an unconsented mapping would pass Phase G green"
        )
    else:
        assert not fired, (
            f"{statement!r} does not reach the mapper but fires the consent "
            f"gate. Every closure carries imports of this shape, so this "
            f"demands a grant from builds that never map anything"
        )


def test_mapper_root_is_the_full_dotted_path():
    """A truncated root would make the gate fire on unrelated `nxd` imports.

    The parametrised cases above would catch that too, but this names the
    failure directly: `nxd`, `nxd.experimental`, or any other prefix is not a
    safe value for this constant.
    """
    body = _script_body()
    root = re.search(r'^MAPPER_ROOT = "([^"]+)"', body, re.M)
    assert root and root.group(1) == "nxd.experimental.field_mapper", (
        f"MAPPER_ROOT is {root.group(1)!r} if it matched at all; a prefix of "
        f"the harness path demands consent from every closure that imports nxd"
    )


def test_the_legacy_vendored_import_is_denied_by_name(tmp_path):
    """The pre-package spelling must not pass green.

    Before the harness shipped inside `nxd`, the sanctioned contract was to COPY
    `field_mapper/` into the closure root and `import field_mapper`. Every
    closure authored before the move has that shape on disk, and the import
    still resolves at Phase B because the closure root is on `sys.path` — so
    left unmatched this is the worst case the gate has: the transform maps for
    real against the env-fallback key while the gate reports no obligation.

    Denied by name rather than routed through the grant oracle: a vendored copy
    answers for its own spec hash, so no grant bound to it means anything.
    """
    _vendor(tmp_path)
    _spec(tmp_path)
    out = _run_phase_g(
        tmp_path,
        expect_exit=1,
        transform_src=("import dlt\n"
                       "from field_mapper import map_inputs\n"
                       "from nxd import data_product\n"
                       "def go():\n"
                       "    return map_inputs([], spec=None, grant=None,\n"
                       "                      run_dir='', call=None)\n"),
    )
    assert "grant.vendored_harness" in _codes(out), _codes(out)
    # The finding must name the offending module and say what is wrong with it.
    # (The `fix=` remediation is not asserted here: this harness's `diag` stub
    # records only stage/code/path, so asserting on it would test the stub's
    # rendering rather than the gate's message.)
    assert "transform/main.py imports 'field_mapper'" in out, out
    assert "vendored into the closure" in out, out


def test_a_granted_closure_is_not_accused_of_vendoring(tmp_path):
    """The legacy check must not fire on the shape this PR makes canonical.

    A gate that denies the correct spelling as well as the retired one is worse
    than no gate: it makes the fix unreachable.
    """
    _vendor(tmp_path)
    _spec(tmp_path)
    spec_id = _real_spec_id(tmp_path)
    _write(tmp_path, "contracts/grant.json", _grant_doc(spec_id))
    out = _run_phase_g(tmp_path, expect_exit=0)
    assert "grant.vendored_harness" not in _codes(out), _codes(out)
