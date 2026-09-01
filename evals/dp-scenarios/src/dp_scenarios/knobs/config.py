"""Decode deterministic runtime-knob plans used by the tier CLI."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from .broker import BrokerFaultPlan, BrokerFaultShape
from .runtime import KnobError, PlanShape, SupervisorKnobs, TransformWindowSizing
from .workflow import WorkflowSwitchPlan


def _mapping(value: object, location: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise KnobError(f"{location} must be an object")
    return value


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnobError(f"{location} must be a non-empty string")
    return value


def _positive_int(value: object, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise KnobError(f"{location} must be a positive integer")
    return value


def _plan_shape(value: object, location: str) -> PlanShape:
    raw = _mapping(value, location)
    name = _string(raw.get("name"), f"{location}.name")
    calls = raw.get("calls")
    if isinstance(calls, Mapping):
        calls = {
            _string(route, f"{location}.calls key"): _positive_int(
                count, f"{location}.calls[{route!r}]"
            )
            for route, count in calls.items()
        }
    elif not isinstance(calls, int) or isinstance(calls, bool):
        raise KnobError(f"{location}.calls must be an integer or object")
    return PlanShape(name, calls)


def _transform(value: object) -> TransformWindowSizing:
    raw = _mapping(value, "transform_window")
    raw_route_keys = raw.get("route_keys", ())
    if not isinstance(raw_route_keys, Sequence) or isinstance(
        raw_route_keys, (str, bytes, bytearray)
    ):
        raise KnobError("transform_window.route_keys must be an array")
    route_keys = tuple(_string(key, "transform_window.route_keys item") for key in raw_route_keys)
    return TransformWindowSizing.from_plans(
        _plan_shape(raw.get("naive"), "transform_window.naive"),
        _plan_shape(raw.get("bounded"), "transform_window.bounded"),
        per_call_latency_ms=_positive_int(
            raw.get("per_call_latency_ms"), "transform_window.per_call_latency_ms"
        ),
        route_keys=route_keys,
    )


def _broker(value: object) -> BrokerFaultPlan:
    raw = _mapping(value, "broker_fault")
    raw_faults = _mapping(raw.get("faults"), "broker_fault.faults")
    faults: dict[int, BrokerFaultShape] = {}
    for attempt, shape in raw_faults.items():
        try:
            attempt_number = int(attempt)
        except (TypeError, ValueError) as exc:
            raise KnobError(f"broker_fault.faults key {attempt!r} is not an integer") from exc
        faults[attempt_number] = BrokerFaultShape(
            _string(shape, f"broker_fault.faults[{attempt!r}]")
        )
    return BrokerFaultPlan(
        faults,
        _string(raw.get("real_entrypoint"), "broker_fault.real_entrypoint"),
        bind_timeout_s=_positive_int(
            raw.get("bind_timeout_s", 30), "broker_fault.bind_timeout_s"
        ),
        margin_s=_positive_int(raw.get("margin_s", 1), "broker_fault.margin_s"),
    )


def supervisor_knobs_from_mapping(value: Mapping[str, object]) -> SupervisorKnobs:
    """Decode one scenario/epoch object from the CLI plan format."""

    raw = _mapping(value, "knob plan entry")
    unknown = set(raw) - {"transform_window", "broker_fault", "workflow_switch"}
    if unknown:
        raise KnobError(
            "knob plan entry has unknown field(s): " + ", ".join(sorted(map(str, unknown)))
        )

    transform = _transform(raw["transform_window"]) if "transform_window" in raw else None
    broker = _broker(raw["broker_fault"]) if "broker_fault" in raw else None
    workflow_value = raw.get("workflow_switch")
    workflow = None
    if workflow_value is not None:
        workflow_raw = _mapping(workflow_value, "workflow_switch")
        workflow = WorkflowSwitchPlan(
            _string(workflow_raw.get("from_workflow"), "workflow_switch.from_workflow"),
            _string(workflow_raw.get("to_workflow"), "workflow_switch.to_workflow"),
        )
    return SupervisorKnobs(
        transform_window=transform,
        broker_fault=broker,
        workflow_switch=workflow,
    )


def load_knob_plan(path: str | Path) -> dict[tuple[str, int], SupervisorKnobs]:
    """Load a JSON plan keyed by scenario id and one-based epoch.

    The accepted shape is either ``{"scenarios": {id: {"1": {...}}}}`` or
    the inner ``{id: {"1": {...}}}`` object directly.
    """

    target = Path(path)
    try:
        raw_value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise KnobError(f"could not read knob plan {target}: {exc}") from exc
    raw = _mapping(raw_value, "knob plan")
    scenarios = _mapping(raw.get("scenarios", raw), "knob plan.scenarios")
    plan: dict[tuple[str, int], SupervisorKnobs] = {}
    for scenario_id, epochs_value in scenarios.items():
        scenario = _string(scenario_id, "knob plan scenario id")
        epochs = _mapping(epochs_value, f"knob plan.scenarios[{scenario!r}]")
        for epoch_value, knobs_value in epochs.items():
            try:
                epoch = int(epoch_value)
            except (TypeError, ValueError) as exc:
                raise KnobError(
                    f"epoch {epoch_value!r} for {scenario} is not an integer"
                ) from exc
            _positive_int(epoch, f"epoch for {scenario}")
            plan[(scenario, epoch)] = supervisor_knobs_from_mapping(
                _mapping(knobs_value, f"knob plan {scenario} epoch {epoch}")
            )
    return plan


__all__ = ["load_knob_plan", "supervisor_knobs_from_mapping"]
