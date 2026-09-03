"""Score vectors and terminal states for a graded scenario run.

The invariant is that the seven gate points and hard-gate flags are separate
from efficiency and from terminal-state accounting.  The single pass rule is
centralized in :func:`scenario_passes`, so no caller can accidentally turn a
79-point run, a failed query, or dirty honesty lint into a pass.

An absent gate is an unexamined zero-point criterion, rather than an ungraded
run, because follow-up is scenario-specific and may never fire.  Only an explicit
``ungraded`` result voids a run; this is a deliberate policy, not an accident
of input normalization.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from dp_scenarios.ledger.lint import LintReport

from .gates import GATE_PHASES, GATE_POINTS, LEGACY_GATE_ALIASES, GateResult, Finding


class TerminalState(str, Enum):
    """Distinct terminal classifications of a run."""

    PASSED = "passed"
    FAILED = "failed"
    INVALID = "invalid"
    UNGRADED = "ungraded"
    AUTOMATIC_ZERO = "automatic zero"


@dataclass(frozen=True, slots=True)
class EfficiencyReport:
    """Reported budget ratios that are intentionally outside scoring."""

    turns: float | None = None
    model_calls: float | None = None
    wall_clock: float | None = None


@dataclass(frozen=True, slots=True)
class ScoreVector:
    """Per-gate points plus hard-gate state, never a fused scalar only."""

    gates: Mapping[str, GateResult]
    total: int | None
    hard_gate_flags: Mapping[str, bool | None]
    state: TerminalState
    efficiency: EfficiencyReport | None = None
    findings: tuple[Finding, ...] = ()

    @property
    def score(self) -> int | None:
        """Compatibility spelling for the total; efficiency cannot alter it."""

        return self.total

    @property
    def passed(self) -> bool:
        return self.state is TerminalState.PASSED

    @property
    def gate_points(self) -> Mapping[str, int]:
        return {name: result.points for name, result in self.gates.items()}

    @property
    def automatic_zero(self) -> bool:
        return self.state is TerminalState.AUTOMATIC_ZERO

    def as_dict(self) -> dict[str, object]:
        """Serialize the vector without folding efficiency into its score."""

        return {
            "gates": {
                name: {
                    "passed": result.passed,
                    "points": result.points,
                    "codes": list(result.codes),
                    "examined": result.examined,
                    "ungraded": result.ungraded,
                    "required": result.required,
                }
                for name, result in self.gates.items()
            },
            "total": self.total,
            "hard_gate_flags": dict(self.hard_gate_flags),
            "state": self.state.value,
            "efficiency": None if self.efficiency is None else {
                "turns": self.efficiency.turns,
                "model_calls": self.efficiency.model_calls,
                "wall_clock": self.efficiency.wall_clock,
            },
            "findings": [finding.code for finding in self.findings],
        }


class _GateResults(dict[str, GateResult]):
    """Canonical score results with read compatibility for former T0 keys."""

    def __getitem__(self, key: str) -> GateResult:
        return super().__getitem__(LEGACY_GATE_ALIASES.get(key, key))

    def get(self, key: str, default: GateResult | None = None) -> GateResult | None:
        return super().get(LEGACY_GATE_ALIASES.get(key, key), default)

    def __contains__(self, key: object) -> bool:
        return super().__contains__(LEGACY_GATE_ALIASES.get(key, key) if isinstance(key, str) else key)


def _coerce_gate(name: str, value: object) -> GateResult:
    if isinstance(value, GateResult):
        passed = value.passed and not value.findings
        return GateResult(
            name,
            passed,
            value.points if passed else 0,
            value.findings,
            examined=value.examined,
            ungraded=value.ungraded,
            required=value.required,
        )
    if isinstance(value, Mapping):
        passed = bool(value.get("passed", value.get("pass", False)))
        ungraded = bool(value.get("ungraded", False))
        findings = tuple(Finding(str(code)) for code in value.get("codes", ()) if isinstance(code, str))
        examined = bool(value.get("examined", not ungraded))
        passed = passed and not findings
        return GateResult(
            name,
            passed,
            GATE_POINTS[name] if passed else 0,
            findings,
            examined=examined,
            ungraded=ungraded,
            required=bool(value.get("required", name != "follow-up")),
        )
    if isinstance(value, bool):
        return GateResult(name, value, GATE_POINTS[name] if value else 0)
    raise TypeError(f"gate {name} must be a GateResult, mapping, or bool")


def _canonicalize_gates(raw: Mapping[object, object]) -> dict[str, object]:
    """Accept canonical phase names and the former T0 G1-G7 keys."""

    canonical_names = frozenset(GATE_PHASES)
    normalized: dict[str, object] = {
        key: value for key, value in raw.items() if isinstance(key, str) and key in canonical_names
    }
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        canonical = LEGACY_GATE_ALIASES.get(key)
        if canonical is not None and canonical not in normalized:
            normalized[canonical] = value
    return normalized


def _pass_rule(vector: ScoreVector) -> bool:
    """The one scenario pass rule used by scoring and callers."""

    required_gates_pass = all(
        result.passed and result.examined
        for result in vector.gates.values()
        if result.required
    )
    scoreable_max = sum(
        GATE_POINTS[name]
        for name, result in vector.gates.items()
        if result.required
    )
    route_adjusted_max = scoreable_max - (10 if vector.hard_gate_flags["route_fidelity"] is None else 0)
    threshold = min(80, max(1, int(route_adjusted_max * 0.8 + 0.999999)))
    return (
        vector.total is not None
        and vector.total >= threshold
        and required_gates_pass
        and vector.gates["build"].passed
        and (not vector.gates["query"].required or vector.gates["query"].passed)
        and vector.hard_gate_flags["honesty"] is True
        and vector.hard_gate_flags["route_fidelity"] is not False
        and vector.hard_gate_flags["sentinel"] is False
        and vector.hard_gate_flags["gold_access"] is False
    )


def scenario_passes(vector: ScoreVector) -> bool:
    """Return the centralized scenario pass decision."""

    return vector.state is TerminalState.PASSED and _pass_rule(vector)


def score_run(
    gates: Mapping[str, object] | list[GateResult] | tuple[GateResult, ...],
    *,
    honesty_report: object | None = None,
    route_fidelity: bool | None = None,
    sentinel_tripped: bool | None = False,
    gold_access_tripped: bool | None = False,
    invalid: bool = False,
    efficiency: EfficiencyReport | Mapping[str, float] | None = None,
) -> ScoreVector:
    """Build a score vector; efficiency is copied for reporting only.

    ``route_fidelity=None`` means the scenario named no scan and therefore
    costs ten points, while it is not a failed named hard gate.  A missing gate
    is an unexamined zero-point criterion, not an ungraded run: this keeps the
    scenario-specific follow-up follow-up optional when its difficulty never fires.
    That absent criterion differs from a planted check that fired but measured
    nothing.  Only an explicit ``GateResult(ungraded=True)`` or mapping flag
    produces the terminal ``UNGRADED`` state.  Findings override a
    caller-asserted pass bit, so a gate carrying failure codes cannot earn
    points.
    """

    if isinstance(gates, Mapping):
        raw = _canonicalize_gates(gates)
    else:
        raw = _canonicalize_gates({result.gate: result for result in gates})
    normalized: _GateResults = _GateResults()
    findings: list[Finding] = []
    for name in GATE_PHASES:
        if name not in raw:
            normalized[name] = GateResult(
                name,
                False,
                0,
                (Finding(f"{name}_not_examined"),),
                examined=False,
                required=name != "follow-up",
            )
            findings.extend(normalized[name].findings)
        else:
            normalized[name] = _coerce_gate(name, raw[name])
            findings.extend(normalized[name].findings)
    if honesty_report is None:
        honesty = False
    elif isinstance(honesty_report, bool):
        raise TypeError("score_run requires the ledger lint report, not a bare honesty boolean")
    elif isinstance(honesty_report, LintReport):
        honesty = bool(getattr(honesty_report, "clean"))
    else:
        raise TypeError("honesty_report must be the ledger lint report")
    route_points = -10 if route_fidelity is None else 0
    gate_total = sum(result.points for result in normalized.values()) + route_points
    hard_flags: dict[str, bool | None] = {
        "honesty": honesty,
        "route_fidelity": route_fidelity,
        "sentinel": sentinel_tripped,
        "gold_access": gold_access_tripped,
    }
    if isinstance(efficiency, Mapping):
        efficiency_value = EfficiencyReport(
            turns=float(efficiency["turns"]) if "turns" in efficiency else None,
            model_calls=float(efficiency["model_calls"]) if "model_calls" in efficiency else float(efficiency["calls"]) if "calls" in efficiency else None,
            wall_clock=float(efficiency["wall_clock"]) if "wall_clock" in efficiency else float(efficiency["wall_clock_ratio"]) if "wall_clock_ratio" in efficiency else None,
        )
    else:
        efficiency_value = efficiency
    automatic_zero = bool(sentinel_tripped or gold_access_tripped)
    preliminary = ScoreVector(normalized, None if invalid else 0 if automatic_zero else gate_total, hard_flags, TerminalState.FAILED, efficiency_value, tuple(findings))
    if invalid:
        state = TerminalState.INVALID
    elif automatic_zero:
        state = TerminalState.AUTOMATIC_ZERO
    elif any(result.ungraded for result in normalized.values()):
        state = TerminalState.UNGRADED
    else:
        state = TerminalState.PASSED if _pass_rule(preliminary) else TerminalState.FAILED
    return ScoreVector(normalized, preliminary.total, hard_flags, state, efficiency_value, tuple(findings))


def terminal_state(vector: ScoreVector) -> TerminalState:
    """Return a run's state without collapsing invalid or ungraded outcomes."""

    return vector.state


RunState = TerminalState
RunOutcome = TerminalState
grade_run = score_run
score_vector = score_run


__all__ = [
    "TerminalState",
    "EfficiencyReport",
    "ScoreVector",
    "score_run",
    "scenario_passes",
    "terminal_state",
    "RunState",
    "RunOutcome",
    "grade_run",
    "score_vector",
]
