"""An ungraded run reports the reason that actually voided it.

``qualify_run`` used to attach the fixed string ``required_difficulty_not_fired``
to every UNGRADED score, whatever produced it. That is a claim the code never
checked: a planted check that measured nothing, a check with an unrecognized
result, and a genuinely unfired plant all reported as an unfired difficulty.
Read beside ``operator-observations.json`` -- which may say the plant did fire
-- it invited exactly the wrong conclusion about which surface was lying.
"""

from __future__ import annotations

from dp_scenarios.grading.gates import Finding, GateResult
from dp_scenarios.grading.score import score_run
from dp_scenarios.ledger.lint import LintReport
from dp_scenarios.runner.qualification import QualificationDisposition, qualify_run


def _clean_lint() -> LintReport:
    return LintReport(clean=True, findings=[])


def _score(follow_up: GateResult):
    gates = {
        name: GateResult(name, True, 10, ())
        for name in ("intake", "capability", "narrowing", "construction", "build", "query")
    }
    gates["follow-up"] = follow_up
    return score_run(gates, honesty_report=_clean_lint(), route_fidelity=True)


def test_an_ungraded_run_names_the_finding_that_voided_it() -> None:
    """A follow-up check that measured nothing must not be reported as an
    unfired difficulty -- that is a different fact about a different run."""

    score = _score(
        GateResult(
            "follow-up",
            False,
            0,
            (Finding("follow_up_check_ungraded", "planted check fired without a measurable result"),),
            examined=False,
            ungraded=True,
        )
    )

    record = qualify_run(score, replay_status="verified", generated_operator=False)

    assert record.disposition is QualificationDisposition.OBSERVED
    assert record.reasons == ("follow_up_check_ungraded",)
    assert "required_difficulty_not_fired" not in record.reasons


def test_an_actually_unfired_plant_still_says_so() -> None:
    """The complement: when the plant really did not fire, the reason survives."""

    score = _score(
        GateResult(
            "follow-up",
            False,
            0,
            (Finding("required_plant_not_fired", "declared planted difficulty did not fire", ["grain_trap_fanout"]),),
            examined=True,
            ungraded=True,
        )
    )

    record = qualify_run(score, replay_status="verified", generated_operator=False)

    assert record.disposition is QualificationDisposition.OBSERVED
    assert record.reasons == ("required_plant_not_fired",)


def test_an_ungraded_gate_with_no_findings_still_names_a_reason() -> None:
    """The fallback branch: ungraded, but nothing said why.

    A gate can be marked ungraded while carrying no findings -- a check that
    returned an unrecognized shape is the realistic case. Returning an empty
    reason tuple there would hand a reader a run voided for no stated cause,
    which is the same silence the reason derivation exists to remove. The
    fallback must name something, and it must not borrow the unfired-plant
    wording, which would be a claim nothing checked.
    """

    score = _score(GateResult("follow-up", False, 0, (), examined=False, ungraded=True))

    record = qualify_run(score, replay_status="verified", generated_operator=False)

    assert record.disposition is QualificationDisposition.OBSERVED
    assert record.reasons == ("run_ungraded",)
    assert "required_difficulty_not_fired" not in record.reasons
