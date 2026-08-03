"""Phase D — the policy-boundary gate — must bite on a real regression.

The rules Phase D enforces were already shipped as prose and were violated by a
real generated closure anyway: `nxd_decisions` built from a Python literal in
`DERIVED_MODELS`, so the ledger *described* thresholds that lived as literals
elsewhere in the same file. A row reading "EDITABLE." was not editable, and the
prose and the code had already silently diverged.

These tests extract the shipped script from `reference/self-check.md` and run
Phase D's three branches directly, because the failure mode being guarded is a
check that exists but never fires. The first version of Phase D keyed on the
statically-parsed `PHYSICAL_MODELS`, which the shipped transform template writes
as `BASE_MODELS + DERIVED_MODELS` — an expression, not a literal — so it silently
passed the very closure it was written for. That is what these tests pin.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import textwrap
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parents[1]
SELF_CHECK_MD = (
    EVALS_DIR.parent / "src" / "nxd-generate-dp" / "reference" / "self-check.md"
)


PHASE_D_BEGIN = "# === PHASE-D-BEGIN ==="
PHASE_D_END = "# === PHASE-D-END ==="


def _script_body() -> str:
    """The single ``# self_check.py`` fence — the source the agent runs.

    Selected by its ``# self_check.py`` header, not by being the longest fence.
    Length is not an identity: the doc is free to grow a longer example block,
    and picking by size would silently start testing it.
    """
    blocks = re.findall(r"```python\n(.*?)```", SELF_CHECK_MD.read_text(), re.S)
    bodies = [b for b in blocks if b.lstrip().startswith("# self_check.py")]
    assert len(bodies) == 1, f"expected one self_check.py fence, found {len(bodies)}"
    return bodies[0]


def _phase_d_source() -> str:
    """The shipped script's Phase D block, sliced by its anchor comments.

    Anchors rather than content-matching, because the content moved out from
    under the old heuristic. It cut between the first ``derrors = []`` and the
    first ``if derrors:`` inside the longest fence — which silently selects the
    wrong region as soon as either token appears earlier (a comment mentioning
    it) or a sibling phase grows the same shape. Phase E did exactly that: it
    added a second ``eerrors``/``if eerrors:`` pair. A mis-sliced block does not
    fail loudly; it keeps passing while testing nothing.
    """
    body = _script_body()
    start = body.index(PHASE_D_BEGIN) + len(PHASE_D_BEGIN)
    end = body.index(PHASE_D_END)
    assert start < end, "PHASE-D-END must follow PHASE-D-BEGIN"
    return body[start:end]


def _run_phase_d(tmp_path: Path, *, base_models, physical_models,
                 ledger: str | None, transform: str,
                 policy_csvs: dict[str, str] | None = None) -> str:
    """Execute Phase D standalone against a synthetic closure."""
    (tmp_path / "transform").mkdir(exist_ok=True)
    (tmp_path / "transform" / "main.py").write_text(transform, encoding="utf-8")
    if ledger is not None:
        d = tmp_path / "data" / "nxd_decisions"
        d.mkdir(parents=True, exist_ok=True)
        (d / "nxd_decisions.csv").write_text(ledger, encoding="utf-8")
    for rel, content in (policy_csvs or {}).items():
        p = tmp_path / "data" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    harness = textwrap.dedent(f"""
        import ast, sys
        from pathlib import Path
        BASE_MODELS = {base_models!r}
        PHYSICAL_MODELS = {physical_models!r}
    """) + _phase_d_source() + textwrap.dedent("""
        for e in dict.fromkeys(derrors):
            print("FAIL " + e)
        print("PHASE_D_DONE")
    """)
    script = tmp_path / "_phase_d.py"
    script.write_text(harness, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path,
        capture_output=True, text=True,
    )
    assert "PHASE_D_DONE" in proc.stdout, proc.stdout + proc.stderr
    return proc.stdout


CLEAN_TRANSFORM = "BASE_MODELS = ('a',)\nDERIVED_MODELS = ()\n"


def test_phase_d_anchors_are_present():
    """Both anchors must exist, exactly once each, in the right order.

    This is the test that makes the anchors real. Without it, deleting a marker
    while refactoring turns every other test in this file into a collection
    error whose cause is one level removed from the edit that caused it — and
    deleting BOTH would send a future reader back to a length/content heuristic
    because "the anchors were not load-bearing anyway".
    """
    body = _script_body()
    for anchor in (PHASE_D_BEGIN, PHASE_D_END):
        assert body.count(anchor) == 1, (
            f"expected exactly one {anchor!r} in the self_check.py fence, found "
            f"{body.count(anchor)} — evals/tests/test_policy_boundary_phase_d.py "
            f"slices the Phase D block by these markers"
        )
    assert body.index(PHASE_D_BEGIN) < body.index(PHASE_D_END)


def test_phase_d_anchors_bracket_the_real_block():
    """The slice must span the whole gate: its errors list through its last check.

    Pins the anchors to the block's true extent rather than to their own
    existence. If PHASE-D-BEGIN drifts below ``derrors = []`` the harness stops
    defining the list; if PHASE-D-END drifts above the CSV-duplication scan, that
    half of the gate goes untested while every test here still passes.
    """
    src = _phase_d_source()
    assert "derrors = []" in src, "the block must start at or above `derrors = []`"
    assert "if derrors:" not in src, (
        "the slice must stop BEFORE `if derrors:` — the harness prints the "
        "findings itself and the real block's sys.exit would kill it"
    )
    assert "nxd_decisions" in src, "the ledger half of Phase D is outside the slice"
    assert "is landed AND" in src, (
        "the landed-vs-hardcoded half of Phase D is outside the slice"
    )


def test_phase_d_source_is_extractable():
    """If the block moves or is renamed, these tests must fail loudly."""
    src = _phase_d_source()
    assert "nxd_decisions" in src and "derrors" in src
    ast.parse(textwrap.dedent(src))


def test_ledger_generated_in_transform_fails(tmp_path):
    """The exact regression: nxd_decisions promised but not a base model.

    Keyed on the RUNTIME values, not the statically-parsed ones — the shipped
    template writes PHYSICAL_MODELS as an expression, and a gate reading it
    statically never fires.
    """
    out = _run_phase_d(
        tmp_path,
        base_models=("candidates",),
        physical_models=("candidates", "candidate_scoring", "nxd_decisions"),
        ledger=None,
        transform=CLEAN_TRANSFORM,
    )
    assert "FAIL" in out
    assert "not in BASE_MODELS" in out
    assert "editing a row changes nothing" in out


def test_ledger_without_status_column_fails(tmp_path):
    out = _run_phase_d(
        tmp_path,
        base_models=("nxd_decisions",),
        physical_models=("nxd_decisions",),
        ledger="decision_id,category,provenance,ruling\n"
               "w1,weight,user_confirmed,C1 = 25\n",
        transform=CLEAN_TRANSFORM,
    )
    assert "no 'status' column" in out


def test_ledger_with_bad_status_value_fails(tmp_path):
    out = _run_phase_d(
        tmp_path,
        base_models=("nxd_decisions",),
        physical_models=("nxd_decisions",),
        ledger="decision_id,status,provenance,ruling\n"
               "w1,approved,user_confirmed,C1 = 25\n",
        transform=CLEAN_TRANSFORM,
    )
    assert "status has ['approved']" in out


def test_ledger_without_provenance_column_fails(tmp_path):
    """status alone cannot say who authored a ruling.

    A ledger carrying only status is the defect this column exists to close: a
    weight the user supplied and a threshold the agent invented to fill an
    underspecified rubric are the same row there.
    """
    out = _run_phase_d(
        tmp_path,
        base_models=("nxd_decisions",),
        physical_models=("nxd_decisions",),
        ledger="decision_id,status,ruling\nw1,confirmed,C1 = 25\n",
        transform=CLEAN_TRANSFORM,
    )
    assert "no 'provenance' column" in out


def test_ledger_with_bad_provenance_value_fails(tmp_path):
    """The vocabulary is closed — that is what makes the class queryable."""
    out = _run_phase_d(
        tmp_path,
        base_models=("nxd_decisions",),
        physical_models=("nxd_decisions",),
        ledger="decision_id,status,provenance,ruling\n"
               "w1,confirmed,agent_invented,C1 = 25\n",
        transform=CLEAN_TRANSFORM,
    )
    assert "provenance has ['agent_invented']" in out


def test_status_and_provenance_are_checked_independently(tmp_path):
    """Two axes, two verdicts — one bad column must not mask the other.

    Written as an ordering trap: if the checks were nested (validate provenance
    only once status is clean, or the reverse), one of these two complaints
    would be silently dropped and half the ledger would go unvalidated.
    """
    out = _run_phase_d(
        tmp_path,
        base_models=("nxd_decisions",),
        physical_models=("nxd_decisions",),
        ledger="decision_id,status,provenance,ruling\n"
               "w1,approved,agent_invented,C1 = 25\n",
        transform=CLEAN_TRANSFORM,
    )
    assert "status has ['approved']" in out
    assert "provenance has ['agent_invented']" in out


def test_missing_provenance_still_reports_bad_status(tmp_path):
    """The absent-column branch must not skip the other column's value check."""
    out = _run_phase_d(
        tmp_path,
        base_models=("nxd_decisions",),
        physical_models=("nxd_decisions",),
        ledger="decision_id,status,ruling\nw1,approved,C1 = 25\n",
        transform=CLEAN_TRANSFORM,
    )
    assert "no 'provenance' column" in out
    assert "status has ['approved']" in out


def test_well_formed_ledger_passes(tmp_path):
    """Every combination of the two axes is legal, including the orthogonal one.

    `confirmed` + `agent_authored` is the row the issue is about: the
    user approved a threshold the AGENT authored. Settled, but not the user's
    value — and the gate must accept it rather than push it toward
    `user_confirmed`.
    """
    out = _run_phase_d(
        tmp_path,
        base_models=("nxd_decisions",),
        physical_models=("nxd_decisions",),
        ledger=("decision_id,status,provenance,ruling\n"
                "w1,confirmed,user_confirmed,C1 = 25\n"
                "w2,confirmed,agent_authored,mid-scale anchors\n"
                "w3,proposed,agent_authored,merchant mapping\n"
                "w4,confirmed,source_derived,observed currency set\n"
                "w5,blocked,deferred,no FX rates supplied\n"),
        transform=CLEAN_TRANSFORM,
    )
    assert "FAIL" not in out


def test_landed_threshold_duplicated_in_code_fails(tmp_path):
    """A value that is both landed and hardcoded is a divergence waiting."""
    out = _run_phase_d(
        tmp_path,
        base_models=("verdict_thresholds",),
        physical_models=("verdict_thresholds",),
        ledger=None,
        transform="threshold = 380.0\nif composite >= 380.0:\n    pass\n",
        policy_csvs={"verdict_thresholds/verdict_thresholds.csv":
                     "verdict,min_score\nADVANCE,380.0\n"},
    )
    assert "is landed AND" in out
    assert "380.0" in out


def test_key_column_named_in_code_is_not_a_violation(tmp_path):
    """A transform legitimately names the KEY it looks a row up by.

    Only the parameter the row carries must not be duplicated. Flagging keys
    would fail every correct closure — the false positive that made the first
    version of this check unusable.
    """
    out = _run_phase_d(
        tmp_path,
        base_models=("rubric",),
        physical_models=("rubric",),
        ledger=None,
        transform="cols = ['c1_backend_depth', 'c2_education']\n",
        policy_csvs={"rubric/rubric.csv":
                     "criterion,weight\nc1_backend_depth,40\nc2_education,25\n"},
    )
    assert "FAIL" not in out


def test_non_policy_csv_is_not_scanned(tmp_path):
    """Source data legitimately shares values with code (a column name, a code).

    Only directories that look like landed policy are compared.
    """
    out = _run_phase_d(
        tmp_path,
        base_models=("candidates",),
        physical_models=("candidates",),
        ledger=None,
        transform="LABEL = 'Senior Engineer'\n",
        policy_csvs={"candidates/candidates.csv":
                     "id,role\n1,Senior Engineer\n"},
    )
    assert "FAIL" not in out
