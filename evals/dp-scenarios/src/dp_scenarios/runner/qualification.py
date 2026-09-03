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
        return QualificationRecord(QualificationDisposition.OBSERVED, replay_status, operator_mode, ("required_difficulty_not_fired",))
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
