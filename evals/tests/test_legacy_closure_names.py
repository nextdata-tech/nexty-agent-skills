"""A closure built before v0.38.0 must still verify.

v0.38.0 renamed the user-owned IR and its artifact family from `dp-spec.*` to
`dp-blueprint.*`. Closures already on disk keep the old spelling, and nothing
rewrites them — so both verifiers have to find a lock that is not named
`dp-blueprint.lock.json`.

Only the LOCK needs a name fallback. The snapshot and proposal filenames travel
inside the lock as `snapshot` / `proposal_snapshot`, so once the lock is found a
legacy closure resolves the rest of itself from its own contents.
`source_basename` is NOT that mechanism — it is write-only provenance and is
never dereferenced, which is what these tests would have caught the first time.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "src" / "nxd-run-job-loop" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dp_diagnostics as dpd  # noqa: E402
import dp_spec_v2 as dpv2  # noqa: E402

pytest.importorskip("yaml")

WORKED_EXAMPLE = REPO / "evals" / "tests" / "fixtures" / "dp-blueprint-v2-valid.md"
SELF_CHECK = SCRIPTS / "self_check.py"


def _approved_spec_text(source: str | None = None) -> str:
    """Approval is a hash binding, not a `status:` string swap."""
    parsed = dpv2.parse(source if source is not None else WORKED_EXAMPLE.read_text(encoding="utf-8"))
    return dpv2.approve(parsed, base_hash=dpv2.semantic_hash(parsed))


def _approved_v2_spec(tmp_path: Path) -> Path:
    spec = tmp_path / "dp-blueprint.md"
    spec.write_text(_approved_spec_text(), encoding="utf-8")
    return spec


def _legacy_closure(tmp_path: Path) -> Path:
    """A closure written today, then renamed to the pre-v0.38.0 spelling.

    Built through the real `lock write` rather than hand-authored, so the hashes
    are genuine and the only difference from a fresh closure is the naming.
    """
    spec = _approved_v2_spec(tmp_path)
    closure = tmp_path / "closure"
    closure.mkdir()
    dpd.write_lock(spec, closure, plugin_version="0.28.0")

    lock_path = closure / dpd.CLOSURE_LOCK
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    legacy_snapshot = "dp-spec.approved.md"
    (closure / lock["snapshot"]).rename(closure / legacy_snapshot)
    lock["snapshot"] = legacy_snapshot
    lock["source_basename"] = "dp-spec.md"
    (closure / dpd.LEGACY_CLOSURE_LOCK).write_text(
        json.dumps(lock, indent=2) + "\n", encoding="utf-8"
    )
    lock_path.unlink()
    return closure


def test_lock_verify_accepts_a_legacy_named_closure(tmp_path: Path):
    """The reproduction that produced the original finding: rc=1, lock_missing."""
    report = dpd.verify_lock(_legacy_closure(tmp_path)).to_dict()
    assert report["ok"] is True, [d["code"] for d in report["diagnostics"]]
    assert dpd.validate_report(report) == []


def test_lock_verify_still_cross_checks_the_live_spec_on_a_legacy_closure(tmp_path: Path):
    closure = _legacy_closure(tmp_path)
    live = tmp_path / "dp-blueprint.md"
    live.write_text(
        _approved_spec_text(
            WORKED_EXAMPLE.read_text(encoding="utf-8").replace(
                "finance review", "finance audit", 1
            )
        ),
        encoding="utf-8",
    )
    report = dpd.verify_lock(closure, live).to_dict()
    assert report["ok"] is False
    assert "closure.live_spec_diverged" in [d["code"] for d in report["diagnostics"]]


def test_read_lock_finds_the_legacy_lock(tmp_path: Path):
    lock = dpd.read_lock(_legacy_closure(tmp_path))
    assert lock["schema"] == dpd.LOCK_SCHEMA_ID
    assert lock["snapshot"] == "dp-spec.approved.md"


def test_diagnostics_name_the_legacy_lock_they_actually_read(tmp_path: Path):
    """An error must point at the file that is there, not at the current name."""
    closure = _legacy_closure(tmp_path)
    (closure / dpd.LEGACY_CLOSURE_LOCK).write_text("{ not json", encoding="utf-8")
    report = dpd.verify_lock(closure).to_dict()
    paths = [d.get("path") for d in report["diagnostics"]]
    assert f"closure:{dpd.LEGACY_CLOSURE_LOCK}" in paths
    assert f"closure:{dpd.CLOSURE_LOCK}" not in paths


def test_a_closure_missing_both_names_reports_the_current_one(tmp_path: Path):
    """No lock at all is a different fault, and must not advertise the retired name."""
    closure = tmp_path / "closure"
    closure.mkdir()
    report = dpd.verify_lock(closure).to_dict()
    assert report["ok"] is False
    missing = [d for d in report["diagnostics"] if d["code"] == "closure.lock_missing"]
    assert missing, [d["code"] for d in report["diagnostics"]]
    assert missing[0]["path"] == f"closure:{dpd.CLOSURE_LOCK}"
    assert dpd.CLOSURE_LOCK in missing[0]["message"]


def test_resolve_prefers_the_current_name_when_both_exist(tmp_path: Path):
    closure = tmp_path / "closure"
    closure.mkdir()
    (closure / dpd.CLOSURE_LOCK).write_text("{}", encoding="utf-8")
    (closure / dpd.LEGACY_CLOSURE_LOCK).write_text("{}", encoding="utf-8")
    assert dpd.resolve_closure_lock(closure).name == dpd.CLOSURE_LOCK


def test_explicit_lock_path_falls_back_for_a_legacy_closure(tmp_path: Path):
    """The resume playbook hands the agent a literal --lock path.

    `context-and-resume.md` and `failure-handling.md` both print
    `--lock <closure>/dp-blueprint.lock.json`. Running that verbatim against the
    very closures the fallback exists for used to fail with ENOENT, while
    `lock verify <closure>` on the same closure passed.
    """
    closure = _legacy_closure(tmp_path)
    asked = closure / dpd.CLOSURE_LOCK
    assert not asked.exists()
    assert dpd.resolve_lock_path(asked).name == dpd.LEGACY_CLOSURE_LOCK

    record = dpd.record_init(closure / "build-record.json", asked)
    assert record["compiled_from"] == dpd.read_lock(closure)["spec_hash"]


def test_explicit_lock_path_leaves_a_genuine_typo_alone(tmp_path: Path):
    """Only the current name substitutes — a typo must still report itself."""
    closure = _legacy_closure(tmp_path)
    typo = closure / "dp-blueprnt.lock.json"
    assert dpd.resolve_lock_path(typo) == typo


def test_lock_write_removes_the_pair_it_supersedes(tmp_path: Path):
    """Two approved plans in one closure is the failure byte-copying removes."""
    closure = _legacy_closure(tmp_path)
    spec = closure.parent / "dp-blueprint.md"
    _, report = dpd.write_lock(spec, closure, plugin_version="0.38.0")

    names = sorted(p.name for p in closure.iterdir())
    assert dpd.CLOSURE_LOCK in names and dpd.CLOSURE_SNAPSHOT in names
    assert "dp-spec.lock.json" not in names, (
        "the superseded legacy lock is still here — every reader prefers the "
        "new names, so this stale pair would never be looked at or reported"
    )
    assert "dp-spec.approved.md" not in names
    codes = [d["code"] for d in report.to_dict()["diagnostics"]]
    assert "closure.legacy_artifact_superseded" in codes, "the sweep must say so"


# --------------------------------------------------------------- self_check ---
# self_check.py is copied into the closure and run there with a bare
# interpreter, so it carries its own inlined twin of the fallback.
#
# Phase C is asserted over the shipped source rather than by running the script,
# for the reason test_reach_gate_phase_e.py already documents: reaching Phase C
# needs a complete valid closure (models.py, spec.py, transform/, data/), and a
# fixture that fails an earlier phase exits first and passes VACUOUSLY. The
# first draft of this file made exactly that mistake — three "code not in
# codes" assertions went green against a closure whose Phase C never ran.
# finish() is the exception: it runs whatever the phases did, so the spec_hash
# read below is exercised for real.


def _script_body() -> str:
    return SELF_CHECK.read_text(encoding="utf-8")


def _slice(start: str, end: str) -> str:
    body = _script_body()
    i = body.index(start)
    return body[i:body.index(end, i)]


def _closure_path_module():
    """Execute the shipped constants + resolver, so this tests real behavior."""
    ns: dict = {"Path": Path}
    exec(compile(_slice('CLOSURE_SNAPSHOT = ', 'DIAGS = []'), "self_check", "exec"), ns)
    return ns


def _run_self_check(closure: Path) -> dict:
    """Run the shipped script the way a closure does: cwd = the closure root."""
    (closure / "self_check.py").write_bytes(SELF_CHECK.read_bytes())
    proc = subprocess.run(
        [sys.executable, "self_check.py", "--json"],
        cwd=closure, capture_output=True, text=True,
    )
    assert proc.stdout.strip(), proc.stderr
    assert "KeyError" not in proc.stderr, proc.stderr
    return json.loads(proc.stdout)


def test_self_check_reports_spec_hash_from_a_legacy_lock(tmp_path: Path):
    """The one drift site with no diagnostic at all: a bare except yielding null.

    Runs the real script; finish() emits the JSON report regardless of which
    phases were reached, so this is not vacuous.
    """
    report = _run_self_check(_legacy_closure(tmp_path))
    assert report["spec_hash"] is not None


def test_closure_path_prefers_current_then_falls_back(tmp_path: Path, monkeypatch):
    ns = _closure_path_module()
    closure_path, snapshot = ns["closure_path"], ns["CLOSURE_SNAPSHOT"]
    monkeypatch.chdir(tmp_path)

    # Neither present: report the name a fresh closure should have.
    assert closure_path(snapshot).name == snapshot
    # Legacy only: resolve it.
    (tmp_path / ns["LEGACY"][snapshot]).write_text("x", encoding="utf-8")
    assert closure_path(snapshot).name == ns["LEGACY"][snapshot]
    # Both: current wins.
    (tmp_path / snapshot).write_text("x", encoding="utf-8")
    assert closure_path(snapshot).name == snapshot


def test_the_legacy_map_covers_the_names_resolved_by_name():
    """Only artifacts resolved BY NAME belong here.

    The proposal snapshot is deliberately absent: its filename travels inside
    the lock, so a legacy entry for it could never fire, and freezing a dead
    entry in a test makes a future reader maintain a fallback that cannot run.
    """
    ns = _closure_path_module()
    assert set(ns["LEGACY"]) == {ns["CLOSURE_SNAPSHOT"], ns["CLOSURE_LOCK"]}
    assert ns["LEGACY"][ns["CLOSURE_LOCK"]] == dpd.LEGACY_CLOSURE_LOCK, (
        "the inlined twin must agree with the shared helper it cannot import"
    )


def test_closure_path_never_raises_on_a_name_with_no_legacy_spelling():
    """An unguarded LEGACY[name] would crash the whole in-closure run."""
    ns = _closure_path_module()
    assert ns["closure_path"]("build-record.json").name == "build-record.json"
    assert ns["closure_path"](ns["CLOSURE_PROPOSAL"]).name == ns["CLOSURE_PROPOSAL"]


def test_lock_verify_names_the_snapshot_the_lock_declared(tmp_path: Path):
    """A missing snapshot must be reported under the name the lock declared."""
    closure = _legacy_closure(tmp_path)
    declared = dpd.read_lock(closure)["snapshot"]
    assert declared == "dp-spec.approved.md"
    (closure / declared).unlink()

    report = dpd.verify_lock(closure).to_dict()
    paths = [d["path"] for d in report["diagnostics"]
             if d["code"] == "closure.spec_snapshot_missing"]
    assert paths == [f"closure:{declared}"], report["diagnostics"]


def test_phase_c_c1_reports_the_resolved_snapshot_not_the_constant():
    """C1's twin of the above, asserted over the source.

    Phase C cannot be reached on a fixture thin enough to build here (see the
    section note), so a runtime comparison of the two verifiers passes
    vacuously — Phase C emits nothing at all. Pin the source instead.

    C1 used the CLOSURE_SNAPSHOT constant while every other Phase C branch used
    the resolved name, so a legacy closure with a deleted snapshot got
    `closure:dp-spec.approved.md` from `lock verify` and
    `closure:dp-blueprint.approved.md` from Phase C: two verifiers, one
    closure, two filenames — the disagreement the lock-resolved snapshot exists
    to prevent.
    """
    c1 = _slice("# C1 / C2 — the approved plan", "lock = None")
    assert 'f"{snap_name} is missing from the closure root' in c1, (
        "C1's message must name the snapshot the lock declared"
    )
    assert "(Step 6a).\", snap_name)" in c1, (
        "C1's path argument must name the snapshot the lock declared"
    )
    assert "CLOSURE_SNAPSHOT" not in c1, (
        "the constant here sends a legacy closure's reader after the wrong file"
    )
    # C2 is deliberately NOT part of this: it fires only when neither lock name
    # exists, so CLOSURE_LOCK is the correct answer there.
    c2 = _slice("lock = None", "    try:")
    assert "CLOSURE_LOCK" in c2


def test_phase_c_probes_the_closure_through_the_resolver():
    """No artifact filename may be probed as a literal inside Phase C.

    A literal here is invisible to the fallback: the file is simply not found,
    and C8's scan loop skips a missing entry with no diagnostic at all.
    """
    phase_c = _slice("# C1 / C2 — the approved plan", "PHASE C FAILED — closure-record gate")
    for probe in ('Path("dp-blueprint', "Path('dp-blueprint"):
        assert probe not in phase_c, f"Phase C probes {probe!r} directly"
    assert "lockp = closure_path(CLOSURE_LOCK)" in _script_body()
    # The snapshot is resolved from the LOCK, not guessed by name — the name
    # fallback is only the last resort for an unreadable lock. Guessing here
    # would let `lock verify` and Phase C disagree about one closure.
    assert "_snap_ref, _snap_escaped = _lock_snapshot_ref(lockp)" in _script_body()
    assert "snap = _snap_ref if _snap_ref is not None else closure_path(CLOSURE_SNAPSHOT)" in _script_body()
    assert "closure_path(CLOSURE_LOCK).read_text" in _script_body(), (
        "finish()'s spec_hash read must resolve too — its bare except makes a "
        "stale name silent"
    )
    assert 'scan = ["README.md", snap_name,' in phase_c, (
        "C8 must scan the approved plan under the name the closure actually "
        "uses, or a legacy closure's plan goes unscanned for escaping references"
    )


def test_every_code_self_check_emits_is_registered_in_its_own_table():
    """`diag()` does an unguarded CODES[code]; an unregistered code is a crash.

    `closure.spec_hash_mismatch` was emitted from three Phase C branches while
    absent from this table, so a snapshot/lock version disagreement — exactly
    what a botched rename produces — took the whole self-check down with a
    KeyError instead of reporting the mismatch. The sibling vocab test checks
    self_check's codes against the SHARED registry; this checks them against
    self_check's own inlined one, which is the dict actually subscripted.
    """
    ns: dict = {}
    exec(compile(_slice("CODES = {}", "JSON_MODE ="), "self_check", "exec"), ns)
    registered = ns["CODES"]

    # cerr(code, ...) but diag(stage, code, ...). Read the code from its own
    # slot, and skip the call when it is not positional there — reading args[0]
    # as a fallback would collect the STAGE string and fail a legal call.
    slot = {"cerr": 0, "diag": 1}
    tree = ast.parse(_script_body())
    emitted = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        i = slot.get(getattr(node.func, "id", None))
        if i is None or len(node.args) <= i:
            continue
        arg = node.args[i]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            emitted.add(arg.value)

    unregistered = sorted(c for c in emitted if c not in registered)
    assert not unregistered, (
        f"emitted but not in self_check's CODES table: {unregistered} — "
        "diag() will raise KeyError instead of reporting these"
    )
    assert "closure.spec_hash_mismatch" in registered
