"""Batch statistics built on nxd_eval's Wilson and McNemar primitives.

The invariant is that invalid runs do not enter rates, demonstrated-once
results have no percentage representation, and paired changes are refused
unless the ledger manifest proves a one-field comparison on the same fixture
and operator script.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from dp_scenarios.ledger import Comparability, Manifest
from nxd_eval.stats import ConfidenceInterval, McNemarResult, mcnemar_paired, wilson_ci

from .score import ScoreVector, TerminalState


class RepeatabilityTier(str, Enum):
    """Scenario-declared repeatability tiers."""

    DETERMINISTIC = "deterministic"
    MOCK_SOURCE = "mock-source"
    DEMONSTRATED_ONCE = "demonstrated-once"


@dataclass(frozen=True, slots=True)
class GateRate:
    """One gate's observed rate and nxd_eval Wilson interval."""

    gate: str
    passed: int
    examined: int
    interval: ConfidenceInterval

    @property
    def rate(self) -> float:
        return self.interval.p_hat

    @property
    def lower_bound(self) -> float:
        return self.interval.low

    @property
    def percentage(self) -> float:
        return self.rate * 100.0


@dataclass(frozen=True, slots=True)
class RateReport:
    """Per-gate rates for valid, non-single-shot observations."""

    rates: Mapping[str, GateRate]
    excluded_invalid: int = 0
    discounted_twins: int = 0


@dataclass(frozen=True, slots=True)
class DemonstratedOnce:
    """A one-shot observation with deliberately no rate or percentage field."""

    state: str = "demonstrated-once"
    gates: Mapping[str, bool] | None = None

    def as_dict(self) -> dict[str, object]:
        return {"state": self.state, "gates": dict(self.gates or {})}


@dataclass(frozen=True, slots=True)
class RepeatabilityReport:
    """Declared-tier certification result."""

    tier: RepeatabilityTier
    required_epochs: int
    observed_epochs: int
    certified: bool
    rates: RateReport | None = None
    demonstrated_once: DemonstratedOnce | None = None


def _state(value: object) -> TerminalState | None:
    if isinstance(value, ScoreVector):
        return value.state
    if isinstance(value, Mapping):
        raw = value.get("state", value.get("outcome"))
        try:
            return TerminalState(raw) if raw is not None else None
        except ValueError:
            return None
    return None


def _gate_passed(value: object, gate: str) -> bool:
    passed, _examined = _gate_observation(value, gate)
    return passed


def _gate_observation(value: object, gate: str) -> tuple[bool, bool]:
    """Return a gate's pass bit and its own examined bit."""

    if isinstance(value, ScoreVector):
        result = value.gates.get(gate)
        if result is None:
            return False, False
        return result.passed and value.state is not TerminalState.AUTOMATIC_ZERO, result.examined
    if isinstance(value, Mapping):
        gates = value.get("gates", value)
        if not isinstance(gates, Mapping) or gate not in gates:
            return False, False
        gate_value = gates[gate]
        if isinstance(gate_value, Mapping):
            examined = bool(gate_value.get("examined", not gate_value.get("ungraded", False)))
            passed = bool(gate_value.get("passed", gate_value.get("pass", False)))
        else:
            examined = True
            passed = bool(gate_value)
        state = _state(value)
        return passed and state is not TerminalState.AUTOMATIC_ZERO, examined
    return False, False


def _repeatability_tier(value: object) -> RepeatabilityTier | None:
    if not isinstance(value, Mapping):
        return None
    raw = value.get("repeatability_tier", value.get("tier"))
    try:
        return RepeatabilityTier(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _scenario_id(value: object) -> str | None:
    if isinstance(value, Mapping):
        raw = value.get("scenario_id", value.get("scenario"))
        return str(raw) if raw is not None else None
    return None


def discount_twins(runs: Sequence[object], twins: Mapping[str, str] | None = None) -> tuple[list[object], int]:
    """Keep one observation per declared twin cluster."""

    if not twins:
        return list(runs), 0
    kept: list[object] = []
    seen: set[str] = set()
    discounted = 0
    for run in runs:
        scenario = _scenario_id(run)
        cluster = twins.get(scenario, scenario) if scenario is not None else None
        if cluster is not None and cluster in seen:
            discounted += 1
            continue
        if cluster is not None:
            seen.add(cluster)
        kept.append(run)
    return kept, discounted


def gate_pass_rates(runs: Sequence[object], *, twins: Mapping[str, str] | None = None, alpha: float = 0.05) -> RateReport:
    """Return Wilson rates with per-gate denominators and no one-shot rates."""

    selected, discounted = discount_twins(runs, twins)
    if any(_repeatability_tier(run) is RepeatabilityTier.DEMONSTRATED_ONCE for run in selected):
        raise ValueError("demonstrated-once observations cannot be represented as rates")
    valid = [run for run in selected if _state(run) is not TerminalState.INVALID]
    if len(valid) < 2:
        raise ValueError("a rate request requires at least two valid observations")
    rates: dict[str, GateRate] = {}
    for gate in ("intake", "capability", "narrowing", "construction", "build", "query", "follow-up"):
        passed = 0
        examined = 0
        for run in valid:
            gate_passed, gate_examined = _gate_observation(run, gate)
            if gate_examined:
                examined += 1
                passed += gate_passed
        if examined:
            rates[gate] = GateRate(gate, passed, examined, wilson_ci(passed, examined, alpha=alpha))
    return RateReport(rates=rates, excluded_invalid=len(selected) - len(valid), discounted_twins=discounted)


def repeatability_plan(tier: RepeatabilityTier | str) -> int:
    """Return the epoch count declared by a scenario tier."""

    tier_value = RepeatabilityTier(tier)
    return {RepeatabilityTier.DETERMINISTIC: 5, RepeatabilityTier.MOCK_SOURCE: 3, RepeatabilityTier.DEMONSTRATED_ONCE: 1}[tier_value]


def repeatability_certificate(runs: Sequence[object], tier: RepeatabilityTier | str | object) -> RepeatabilityReport:
    """Certify only the scenario-declared repeatability protocol."""

    declared = tier if not isinstance(tier, (RepeatabilityTier, str)) else None
    tier_value = RepeatabilityTier(getattr(declared, "tier", tier))
    required = int(getattr(declared, "epochs", repeatability_plan(tier_value)))
    certification_rule = str(getattr(declared, "certification_rule", "wilson_lower_bound"))
    certification_gates = tuple(getattr(declared, "gates", ("build", "query")))
    lower_bound = getattr(declared, "lower_bound", 0.90)
    confidence = getattr(declared, "confidence", 0.95)
    if tier_value is RepeatabilityTier.DEMONSTRATED_ONCE:
        last = runs[-1] if runs else None
        result = DemonstratedOnce(gates={gate: _gate_passed(last, gate) for gate in certification_gates} if last is not None else {})
        return RepeatabilityReport(tier_value, required, len(runs), False, demonstrated_once=result)
    alpha = 1 - float(confidence) if confidence is not None else 0.05
    report = gate_pass_rates(runs, alpha=alpha)
    if certification_rule == "observed_epochs":
        certified = len(runs) == required and all(
            _gate_observation(run, gate) == (True, True)
            for run in runs
            for gate in certification_gates
        ) and report.excluded_invalid == 0
    else:
        certified = len(runs) == required and all(
            (rate := report.rates.get(gate)) is not None
            and rate.lower_bound >= float(lower_bound)
            for gate in certification_gates
        ) and report.excluded_invalid == 0
    return RepeatabilityReport(tier_value, required, len(runs), certified, rates=report)


def render_rate(value: GateRate | DemonstratedOnce) -> str:
    """Render a rate only for a real batch rate, never a one-shot result."""

    if isinstance(value, DemonstratedOnce):
        raise TypeError("demonstrated-once observations cannot be rendered as rates")
    return f"{value.gate}: {value.rate:.3f} (Wilson lower {value.lower_bound:.3f})"


def _manifest(value: Manifest | Mapping[str, object]) -> Manifest:
    if isinstance(value, Manifest):
        return value
    return Manifest.from_mapping(value, replay=None)


def paired_mcnemar(
    before_manifest: Manifest | Mapping[str, object],
    after_manifest: Manifest | Mapping[str, object],
    before: Sequence[object],
    after: Sequence[object],
    *,
    field_under_test: str | None = None,
) -> McNemarResult:
    """Run McNemar only for identical fixtures/scripts and one changed field."""

    first = _manifest(before_manifest)
    second = _manifest(after_manifest)
    comparison = first.comparable_to(second)
    if comparison.kind is not Comparability.SINGLE_FIELD:
        raise ValueError(f"paired comparison requires exactly one differing manifest field: {comparison.kind.value}")
    field = next(iter(comparison.differing_fields))
    if field_under_test is not None and field != field_under_test:
        raise ValueError(f"manifest field differs outside the requested comparison: {field}")
    if field in {"fixture_dir_hash", "operator_script_hash", "driver_model_id", "driver_sampling_params"}:
        raise ValueError("paired comparison requires identical fixture, operator script and driver")
    if len(before) != len(after):
        raise ValueError("paired comparison requires one outcome per identical trial")
    base = [_gate_passed(value, "query") for value in before]
    current = [_gate_passed(value, "query") for value in after]
    both_right = sum(a and b for a, b in zip(base, current))
    base_only = sum(a and not b for a, b in zip(base, current))
    current_only = sum((not a) and b for a, b in zip(base, current))
    both_wrong = sum((not a) and (not b) for a, b in zip(base, current))
    return mcnemar_paired(both_right, base_only, current_only, both_wrong)


compare_paired = paired_mcnemar
wilson_gate_rates = gate_pass_rates
repeatability = repeatability_certificate
compare_runs = paired_mcnemar
rate_report = gate_pass_rates


__all__ = [
    "RepeatabilityTier",
    "GateRate",
    "RateReport",
    "DemonstratedOnce",
    "RepeatabilityReport",
    "discount_twins",
    "gate_pass_rates",
    "wilson_gate_rates",
    "repeatability_plan",
    "repeatability_certificate",
    "repeatability",
    "render_rate",
    "paired_mcnemar",
    "compare_paired",
    "compare_runs",
    "rate_report",
]
