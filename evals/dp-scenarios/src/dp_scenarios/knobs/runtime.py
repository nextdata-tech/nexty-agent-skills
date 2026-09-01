"""Arithmetic runtime controls and their manifest representation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from dp_scenarios.mockrest.config import ScenarioConfig, load_config


class KnobError(ValueError):
    """Raised when a runtime knob is incomplete or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class PlanShape:
    """Declared call counts for one transform plan.

    ``calls`` may be a total integer or a route-to-count mapping.  Keeping the
    route breakdown in the manifest makes it possible to audit which calls the
    injected latency applies to without consulting a trace.
    """

    name: str
    calls: int | Mapping[str, int]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise KnobError("plan name must be a non-empty string")
        if isinstance(self.calls, bool):
            raise KnobError("plan call count must be an integer or mapping")
        if isinstance(self.calls, int):
            if self.calls < 1:
                raise KnobError("plan call count must be positive")
            return
        if not isinstance(self.calls, Mapping) or not self.calls:
            raise KnobError("plan call counts must be a non-empty mapping")
        for route, count in self.calls.items():
            if not isinstance(route, str) or not route.strip():
                raise KnobError("plan route names must be non-empty strings")
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                raise KnobError(f"plan call count for {route!r} must be a positive integer")

    @property
    def total_calls(self) -> int:
        """Return the declared number of calls in the plan."""

        if isinstance(self.calls, int):
            return self.calls
        return sum(self.calls.values())

    def call_counts(self) -> dict[str, int]:
        """Return a stable route-count mapping for arithmetic and manifests."""

        if isinstance(self.calls, int):
            return {"<total>": self.calls}
        return {str(route): self.calls[route] for route in sorted(self.calls)}


@dataclass(frozen=True, slots=True)
class TransformWindowSizing:
    """A fixed mock-rest latency paired with a transform decision window.

    The window is chosen as ``2 * bounded_calls * latency``.  Consequently the
    bounded upper bound is exactly half the window and a naive plan is safe
    only when it has at least four times as many declared calls.  All values
    are integer arithmetic over declarations; no measured duration enters the
    contract.
    """

    naive: PlanShape
    bounded: PlanShape
    per_call_latency_ms: int
    window_ms: int
    route_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.naive, PlanShape) or not isinstance(self.bounded, PlanShape):
            raise KnobError("transform plans must be PlanShape instances")
        if isinstance(self.per_call_latency_ms, bool) or not isinstance(self.per_call_latency_ms, int):
            raise KnobError("per-call latency must be an integer")
        if self.per_call_latency_ms < 1:
            raise KnobError("per-call latency must be positive")
        if isinstance(self.window_ms, bool) or not isinstance(self.window_ms, int) or self.window_ms < 1:
            raise KnobError("transform window must be a positive integer")
        if self.naive.total_calls * self.per_call_latency_ms < 2 * self.window_ms:
            raise KnobError("naive plan does not reach twice the transform window")
        if self.bounded.total_calls * self.per_call_latency_ms > self.window_ms // 2:
            raise KnobError("bounded plan exceeds half the transform window")
        if any(not isinstance(key, str) or not key.strip() for key in self.route_keys):
            raise KnobError("transform route keys must be non-empty strings")
        if tuple(sorted(set(self.route_keys))) != self.route_keys:
            raise KnobError("transform route keys must be unique and sorted")

    @classmethod
    def from_plans(
        cls,
        naive: PlanShape,
        bounded: PlanShape,
        *,
        per_call_latency_ms: int,
        route_keys: Sequence[str] = (),
    ) -> "TransformWindowSizing":
        """Construct a sizing whose bounds are true by construction."""

        if not isinstance(naive, PlanShape) or not isinstance(bounded, PlanShape):
            raise KnobError("transform plans must be PlanShape instances")
        if isinstance(per_call_latency_ms, bool) or not isinstance(per_call_latency_ms, int):
            raise KnobError("per-call latency must be an integer")
        if per_call_latency_ms < 1:
            raise KnobError("per-call latency must be positive")
        if naive.total_calls < 4 * bounded.total_calls:
            raise KnobError(
                "declared naive calls must be at least four times bounded calls "
                "for a two-sided window"
            )
        raw_keys = tuple(route_keys)
        if any(not isinstance(key, str) or not key.strip() for key in raw_keys):
            raise KnobError("transform route keys must be non-empty strings")
        keys = tuple(sorted(set(raw_keys)))
        window_ms = 2 * bounded.total_calls * per_call_latency_ms
        return cls(naive, bounded, per_call_latency_ms, window_ms, keys)

    @property
    def naive_lower_bound_ms(self) -> int:
        return self.naive.total_calls * self.per_call_latency_ms

    @property
    def bounded_upper_bound_ms(self) -> int:
        return self.bounded.total_calls * self.per_call_latency_ms

    def arithmetic(self) -> dict[str, object]:
        """Return the complete checkable arithmetic for the run manifest."""

        naive_required = 2 * self.window_ms
        bounded_allowed = self.window_ms // 2
        return {
            "naive_plan": self.naive.name,
            "naive_calls": self.naive.call_counts(),
            "naive_total_calls": self.naive.total_calls,
            "naive_lower_bound_ms": self.naive_lower_bound_ms,
            "naive_required_ms": naive_required,
            "naive_margin_ms": self.naive_lower_bound_ms - naive_required,
            "bounded_plan": self.bounded.name,
            "bounded_calls": self.bounded.call_counts(),
            "bounded_total_calls": self.bounded.total_calls,
            "bounded_upper_bound_ms": self.bounded_upper_bound_ms,
            "bounded_allowed_ms": bounded_allowed,
            "bounded_margin_ms": bounded_allowed - self.bounded_upper_bound_ms,
            "per_call_latency_ms": self.per_call_latency_ms,
            "window_ms": self.window_ms,
            "route_keys": list(self.route_keys),
            "bounds_hold": (
                self.naive_lower_bound_ms >= naive_required
                and self.bounded_upper_bound_ms <= bounded_allowed
            ),
            "method": "declared_call_count_times_fixed_latency",
        }

    def to_manifest(self) -> dict[str, object]:
        return {"enabled": True, "arithmetic": self.arithmetic()}


def _as_config(config: ScenarioConfig | str | Path | Mapping[str, Any]) -> ScenarioConfig:
    if isinstance(config, ScenarioConfig):
        return config
    return load_config(config)


def apply_transform_latency(
    config: ScenarioConfig | str | Path | Mapping[str, Any],
    sizing: TransformWindowSizing,
) -> ScenarioConfig:
    """Return a route table with the declared fixed latency injected.

    The returned config is a new frozen value.  Existing route behavior is
    otherwise preserved, and the control port is never delayed because only
    declared data routes are replaced.
    """

    if not isinstance(sizing, TransformWindowSizing):
        raise KnobError("transform sizing must be a TransformWindowSizing instance")
    loaded = _as_config(config)
    selected = set(sizing.route_keys)
    routes = tuple(
        replace(
            route,
            latency_ms=sizing.per_call_latency_ms,
        )
        if not selected or f"{route.method} {route.path}" in selected or route.path in selected
        else route
        for route in loaded.routes
    )
    if selected:
        available = {route.path for route in loaded.routes} | {
            f"{route.method} {route.path}" for route in loaded.routes
        }
        missing = sorted(selected - available)
        if missing:
            raise KnobError("transform route key(s) not found: " + ", ".join(missing))
    return replace(loaded, routes=routes)


@dataclass(frozen=True, slots=True)
class SupervisorKnobs:
    """The explicit per-run set of controls; all three are off by default."""

    transform_window: TransformWindowSizing | None = None
    broker_fault: object | None = None
    workflow_switch: object | None = None

    @classmethod
    def off(cls) -> "SupervisorKnobs":
        return cls()

    def to_manifest(self, *, attempt: int = 1) -> dict[str, object]:
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise KnobError("attempt must be a positive integer")
        transform = (
            self.transform_window.to_manifest()
            if self.transform_window is not None
            else {"enabled": False}
        )
        if self.broker_fault is None:
            broker: dict[str, object] = {"enabled": False, "active_attempt": attempt, "active_fault": "none"}
        else:
            broker = self.broker_fault.to_manifest(attempt=attempt)  # type: ignore[union-attr]
        workflow = (
            self.workflow_switch.to_manifest()  # type: ignore[union-attr]
            if self.workflow_switch is not None
            else {"enabled": False}
        )
        return {
            "schema_version": 1,
            "transform_window": transform,
            "broker_fault": broker,
            "workflow_switch": workflow,
        }
