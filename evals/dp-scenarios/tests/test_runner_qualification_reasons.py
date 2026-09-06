"""An ungraded run reports the reason that actually voided it.

``qualify_run`` used to attach the fixed string ``required_difficulty_not_fired``
to every UNGRADED score, whatever produced it. That is a claim the code never
checked: a planted check that measured nothing, a check with an unrecognized
result, and a genuinely unfired plant all reported as an unfired difficulty.
Read beside ``operator-observations.json`` -- which may say the plant did fire
-- it invited exactly the wrong conclusion about which surface was lying.
"""

from __future__ import annotations

from dp_scenarios.grading.gates import GATE_PHASES, GATE_POINTS, Finding, GateResult
from dp_scenarios.grading.score import ScoreVector, TerminalState, score_run
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


def _passing_score():
    return score_run(
        {name: GateResult(name, True, GATE_POINTS[name]) for name in GATE_PHASES},
        honesty_report=_clean_lint(),
        route_fidelity=True,
    )


def _passing_score_with_waivers():
    gates = {name: GateResult(name, True, GATE_POINTS[name]) for name in GATE_PHASES}
    gates["capability"] = GateResult(
        "capability",
        False,
        0,
        (Finding("capability_shortfall_not_staged"),),
        examined=False,
        required=False,
    )
    gates["narrowing"] = GateResult(
        "narrowing",
        False,
        0,
        (Finding("narrowing_change_not_staged"),),
        examined=False,
        required=False,
    )
    return score_run(gates, honesty_report=_clean_lint(), route_fidelity=True)


def test_a_driver_authored_run_is_capped_below_certified_with_its_own_reason() -> None:
    """A model authored the operator's words, so nothing here is repeatable.

    The cap has to be its own reason code, not the generated-surface one: a
    reader deciding whether the evidence supports a claim needs to know which
    surface was non-deterministic.
    """

    record = qualify_run(
        _passing_score(),
        replay_status="not-attempted",
        generated_operator=False,
        driver=True,
    )

    assert record.disposition is QualificationDisposition.QUALIFIED
    assert record.operator_mode == "driver"
    assert record.reasons == ("driver_operator_is_capped_below_certified",)


def test_a_driver_run_stays_capped_even_when_repeatability_is_certified() -> None:
    certified = qualify_run(
        _passing_score(),
        replay_status="verified",
        generated_operator=False,
        driver=True,
        repeatability_certified=True,
    )

    assert certified.disposition is QualificationDisposition.QUALIFIED
    assert certified.operator_mode == "driver"
    assert certified.reasons == ("driver_operator_is_capped_below_certified",)

    # Control: the identical call without the driver flag reaches CERTIFIED,
    # so the two assertions above are carried by the cap and not by the score.
    scripted = qualify_run(
        _passing_score(),
        replay_status="verified",
        generated_operator=False,
        driver=False,
        repeatability_certified=True,
    )

    assert scripted.disposition is QualificationDisposition.CERTIFIED


def test_a_scripted_run_is_unchanged_by_the_driver_parameter() -> None:
    record = qualify_run(_passing_score(), replay_status="verified", generated_operator=False)

    assert record.disposition is QualificationDisposition.QUALIFIED
    assert record.operator_mode == "scripted"
    assert record.reasons == ()


def test_certified_and_qualified_records_name_waived_gates() -> None:
    score = _passing_score_with_waivers()

    certified = qualify_run(
        score,
        replay_status="verified",
        generated_operator=False,
        repeatability_certified=True,
    )
    qualified = qualify_run(
        score,
        replay_status="verified",
        generated_operator=False,
        repeatability_certified=False,
    )

    assert certified.disposition is QualificationDisposition.CERTIFIED
    assert certified.reasons == ("gate_waived:capability", "gate_waived:narrowing")
    assert qualified.disposition is QualificationDisposition.QUALIFIED
    assert qualified.reasons == ("gate_waived:capability", "gate_waived:narrowing")


def test_a_truncated_passing_run_is_observed_even_when_repeatability_is_certified() -> None:
    record = qualify_run(
        _passing_score(),
        replay_status="verified",
        generated_operator=False,
        repeatability_certified=True,
        truncated=True,
    )

    assert record.disposition is QualificationDisposition.OBSERVED
    assert record.reasons == ("turn_timeout_truncated",)


def test_a_truncated_ungraded_run_puts_timeout_first_and_keeps_gate_reason() -> None:
    score = _score(
        GateResult(
            "follow-up",
            False,
            0,
            (Finding("required_plant_not_fired", "declared planted difficulty did not fire"),),
            examined=True,
            ungraded=True,
        )
    )

    record = qualify_run(score, replay_status="verified", generated_operator=False, truncated=True)

    assert record.disposition is QualificationDisposition.OBSERVED
    assert record.reasons == ("turn_timeout_truncated", "required_plant_not_fired")


def test_a_truncated_replay_run_keeps_both_caps_with_the_timeout_first() -> None:
    record = qualify_run(
        _passing_score(),
        replay_status="verified",
        generated_operator=False,
        repeatability_certified=True,
        validation_mode="replay",
        truncated=True,
    )

    assert record.disposition is QualificationDisposition.OBSERVED
    assert record.reasons == ("turn_timeout_truncated", "replay_only_not_live")


def test_a_truncated_rejected_run_keeps_the_score_state_reason_after_the_timeout() -> None:
    score = _score(GateResult("follow-up", False, 0, (Finding("gate_failed", "gate did not pass"),), examined=True))

    record = qualify_run(score, replay_status="verified", generated_operator=False, truncated=True)

    assert record.disposition is QualificationDisposition.REJECTED
    assert record.reasons[0] == "turn_timeout_truncated"
    assert record.reasons[1].startswith("score_state:")
