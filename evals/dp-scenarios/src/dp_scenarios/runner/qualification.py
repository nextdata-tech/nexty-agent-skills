"""Explicit qualification dispositions for scenario evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from dp_scenarios.grading import NOT_STAGED_CODES
from dp_scenarios.grading.score import ScoreVector, TerminalState


class QualificationDisposition(str, Enum):
    """What the retained evidence legitimately supports."""

    CERTIFIED = "CERTIFIED"
    QUALIFIED = "QUALIFIED"
    OBSERVED = "OBSERVED"
    REJECTED = "REJECTED"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class QualificationRecord:
    """Machine-readable disposition with the evidence boundary behind it."""

    disposition: QualificationDisposition
    replay_status: str
    operator_mode: str
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "disposition": self.disposition.value,
            "replay_status": self.replay_status,
            "operator_mode": self.operator_mode,
            "reasons": list(self.reasons),
        }


def _ungraded_reasons(score: ScoreVector) -> tuple[str, ...]:
    """Return the codes of the gates that actually voided the run.

    The reason used to be the hardcoded string ``required_difficulty_not_fired``
    for *every* ungraded score, whatever voided it -- a planted check that
    measured nothing, a check with an unrecognized result, and a genuinely
    unfired plant all reported as an unfired difficulty. That is a claim the
    code never checked: a reader comparing ``qualification.json`` against
    ``operator-observations.json`` could see "difficulty not fired" beside
    ``fired_plant_ids: [...]`` and have no way to tell which was true.  The
    reason is now read off the ungraded gates' own findings.
    """

    gate_codes = tuple(
        code
        for result in score.gates.values()
        if result.ungraded
        for code in result.codes
    )
    gate_code_set = set(gate_codes)
    extra_codes = tuple(
        finding.code
        for finding in score.findings
        if finding.code not in gate_code_set
        and finding.code.startswith("checker_skew_")
    )
    codes = tuple(dict.fromkeys((*gate_codes, *extra_codes)))
    return codes or ("run_ungraded",)


def _with_waived_reasons(score: ScoreVector, reasons: tuple[str, ...]) -> tuple[str, ...]:
    """Append declaration-based gate waivers to every qualification surface."""

    waived = tuple(
        f"gate_waived:{name}"
        for name, result in score.gates.items()
        if any(code in NOT_STAGED_CODES for code in result.codes)
    )
    return tuple(dict.fromkeys((*reasons, *waived)))


def qualify_run(
    score: ScoreVector,
    *,
    replay_status: str,
    generated_operator: bool,
    driver: bool = False,
    repeatability_certified: bool = False,
    validation_mode: str = "live",
    operator_mode: str | None = None,
    truncated: bool = False,
    truncation_reason: str | None = None,
) -> QualificationRecord:
    """Map score and replay evidence to a deliberately conservative status.

    ``generated_operator`` is the *cap*: any run whose operator words came
    from a model -- a generated surface or a driver -- cannot be certified.
    ``operator_mode`` is the *label* recorded in the evidence; it defaults to
    the cap's two historical values so a driver run is not mislabelled
    ``generated_surface`` in ``qualification.json`` while
    ``operator-observations.json`` records ``driver``.

    ``truncation_reason`` distinguishes an exhausted operator script from a
    turn that actually hit its deadline.  ``truncated=True`` remains the
    compatibility shorthand for the latter.
    """

    operator_mode = "driver" if driver else (operator_mode or ("generated_surface" if generated_operator else "scripted"))
    if score.state is TerminalState.INVALID:
        return QualificationRecord(
            QualificationDisposition.INVALID,
            replay_status,
            operator_mode,
            _with_waived_reasons(score, ("run_invalid",)),
        )
    incomplete_reason = truncation_reason or ("turn_timeout_truncated" if truncated else None)
    if score.state is TerminalState.UNGRADED:
        reasons = _ungraded_reasons(score)
        if incomplete_reason is not None:
            reasons = (incomplete_reason,) + reasons
        return QualificationRecord(
            QualificationDisposition.OBSERVED,
            replay_status,
            operator_mode,
            _with_waived_reasons(score, reasons),
        )
    if score.state is not TerminalState.PASSED:
        reasons = (f"score_state:{score.state.value}",)
        if incomplete_reason is not None:
            reasons = (incomplete_reason,) + reasons
        return QualificationRecord(
            QualificationDisposition.REJECTED,
            replay_status,
            operator_mode,
            _with_waived_reasons(score, reasons),
        )
    if validation_mode == "replay":
        reasons = ("replay_only_not_live",)
        if truncated:
            reasons = ("turn_timeout_truncated",) + reasons
        return QualificationRecord(
            QualificationDisposition.OBSERVED,
            replay_status,
            operator_mode,
            _with_waived_reasons(score, reasons),
        )
    if incomplete_reason is not None:
        # An incomplete terminal normally leaves later plants unfired, so the
        # run's placement in the tier was never actually reached. Cap it at
        # OBSERVED however clean the rest of the evidence looks.
        return QualificationRecord(
            QualificationDisposition.OBSERVED,
            replay_status,
            operator_mode,
            _with_waived_reasons(score, (incomplete_reason,)),
        )
    if driver:
        # A model authored the operator's words.  Nothing downstream of that
        # is reproducible turn-for-turn, so the run can never be CERTIFIED
        # however many epochs agree.
        return QualificationRecord(
            QualificationDisposition.QUALIFIED,
            replay_status,
            operator_mode,
            _with_waived_reasons(score, ("driver_operator_is_capped_below_certified",)),
        )
    if generated_operator:
        return QualificationRecord(
            QualificationDisposition.QUALIFIED,
            replay_status,
            operator_mode,
            _with_waived_reasons(score, ("generated_operator_is_capped_below_certified",)),
        )
    if replay_status != "verified":
        return QualificationRecord(
            QualificationDisposition.OBSERVED,
            replay_status,
            operator_mode,
            _with_waived_reasons(score, ("replay_not_verified",)),
        )
    if repeatability_certified:
        return QualificationRecord(
            QualificationDisposition.CERTIFIED,
            replay_status,
            operator_mode,
            _with_waived_reasons(score, ()),
        )
    return QualificationRecord(
        QualificationDisposition.QUALIFIED,
        replay_status,
        operator_mode,
        _with_waived_reasons(score, ()),
    )


__all__ = ["QualificationDisposition", "QualificationRecord", "qualify_run"]
