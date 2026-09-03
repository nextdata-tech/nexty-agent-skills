"""Explicit qualification dispositions for scenario evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

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

    codes = tuple(
        dict.fromkeys(
            code
            for result in score.gates.values()
            if result.ungraded
            for code in result.codes
        )
    )
    return codes or ("run_ungraded",)


def qualify_run(
    score: ScoreVector,
    *,
    replay_status: str,
    generated_operator: bool,
    repeatability_certified: bool = False,
    validation_mode: str = "live",
) -> QualificationRecord:
    """Map score and replay evidence to a deliberately conservative status."""

    operator_mode = "generated_surface" if generated_operator else "scripted"
    if score.state is TerminalState.INVALID:
        return QualificationRecord(QualificationDisposition.INVALID, replay_status, operator_mode, ("run_invalid",))
    if score.state is TerminalState.UNGRADED:
        return QualificationRecord(
            QualificationDisposition.OBSERVED, replay_status, operator_mode, _ungraded_reasons(score)
        )
    if score.state is not TerminalState.PASSED:
        return QualificationRecord(QualificationDisposition.REJECTED, replay_status, operator_mode, (f"score_state:{score.state.value}",))
    if validation_mode == "replay":
        return QualificationRecord(
            QualificationDisposition.OBSERVED,
            replay_status,
            operator_mode,
            ("replay_only_not_live",),
        )
    if generated_operator:
        return QualificationRecord(QualificationDisposition.QUALIFIED, replay_status, operator_mode, ("generated_operator_is_capped_below_certified",))
    if replay_status != "verified":
        return QualificationRecord(QualificationDisposition.OBSERVED, replay_status, operator_mode, ("replay_not_verified",))
    if repeatability_certified:
        return QualificationRecord(QualificationDisposition.CERTIFIED, replay_status, operator_mode)
    return QualificationRecord(QualificationDisposition.QUALIFIED, replay_status, operator_mode)


__all__ = ["QualificationDisposition", "QualificationRecord", "qualify_run"]
