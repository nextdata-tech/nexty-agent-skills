"""Deterministic runtime-control tests for the supervisor knobs."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from dp_scenarios.knobs import (
    BrokerFaultPlan,
    BrokerFaultShape,
    EndpointObservation,
    PlanShape,
    SupervisorKnobs,
    TransformWindowSizing,
    WorkflowSwitchEvidence,
    WorkflowSwitchPlan,
    apply_transform_latency,
    broker_entrypoint_path,
    load_knob_plan,
    script_restart_and_switch,
)
from dp_scenarios.mockrest import load_config
from dp_scenarios.runner.environment import PinnedVersions, RunEnvironment


ROOT = Path(__file__).parents[1]


def test_transform_window_bounds_are_symbolic_and_manifested() -> None:
    naive = PlanShape("naive", {"GET /orders": 12, "GET /settlements": 4})
    bounded = PlanShape("bounded", {"GET /orders": 2})
    sizing = TransformWindowSizing.from_plans(
        naive,
        bounded,
        per_call_latency_ms=7,
        route_keys=("GET /orders", "GET /settlements"),
    )

    arithmetic = sizing.arithmetic()
    assert arithmetic["naive_lower_bound_ms"] >= 2 * arithmetic["window_ms"]  # type: ignore[operator]
    assert arithmetic["bounded_upper_bound_ms"] <= arithmetic["window_ms"] // 2  # type: ignore[operator]
    assert arithmetic["bounds_hold"] is True
    assert arithmetic["method"] == "declared_call_count_times_fixed_latency"
    assert arithmetic["naive_calls"] == {"GET /orders": 12, "GET /settlements": 4}

    with pytest.raises(ValueError, match="four times"):
        TransformWindowSizing.from_plans(
            PlanShape("too-small", 3),
            PlanShape("bounded", 1),
            per_call_latency_ms=7,
        )


def test_transform_latency_changes_only_declared_data_routes() -> None:
    config = load_config(ROOT / "scenarios/_examples/mockrest.yaml")
    sizing = TransformWindowSizing.from_plans(
        PlanShape("naive", 12),
        PlanShape("bounded", 1),
        per_call_latency_ms=11,
        route_keys=("GET /market-data",),
    )
    transformed = apply_transform_latency(config, sizing)
    latencies = {f"{route.method} {route.path}": route.latency_ms for route in transformed.routes}
    assert latencies["GET /market-data"] == 11
    assert latencies["GET /orders"] == 0


def test_broker_fault_schedule_is_attempt_keyed_and_repeats_identically() -> None:
    plan = BrokerFaultPlan(
        {1: BrokerFaultShape.OCCUPIED_PORT},
        real_entrypoint="semantic_child.py",
    )
    observed = [plan.fault_for_attempt(attempt) for attempt in (1, 2, 1, 2)]
    assert observed == [
        BrokerFaultShape.OCCUPIED_PORT,
        None,
        BrokerFaultShape.OCCUPIED_PORT,
        None,
    ]
    assert plan.environment_for_attempt(1)["NXD_EVAL_BROKER_FAULT"] == "occupied_port"
    assert plan.environment_for_attempt(2)["NXD_EVAL_BROKER_FAULT"] == "none"
    assert plan.to_manifest(attempt=1)["active_fault"] == "occupied_port"
    assert plan.to_manifest(attempt=2)["active_fault"] == "none"
    sleep_plan = BrokerFaultPlan(
        {1: BrokerFaultShape.SLEEP_PAST_BIND_TIMEOUT},
        real_entrypoint="semantic_child.py",
        bind_timeout_s=30,
        margin_s=2,
    )
    assert sleep_plan.environment_for_attempt(1)["NXD_EVAL_BROKER_FAULT"] == "sleep_past_bind_timeout"
    assert int(sleep_plan.environment_for_attempt(1)["NXD_EVAL_BROKER_BIND_TIMEOUT_S"]) + int(
        sleep_plan.environment_for_attempt(1)["NXD_EVAL_BROKER_MARGIN_S"]
    ) == 32


def test_json_knob_plan_decodes_scenario_epochs(tmp_path: Path) -> None:
    path = tmp_path / "knobs.json"
    path.write_text(
        json.dumps(
            {
                "scenarios": {
                    "scenario-a": {
                        "1": {
                            "transform_window": {
                                "naive": {"name": "naive", "calls": 8},
                                "bounded": {"name": "bounded", "calls": 1},
                                "per_call_latency_ms": 5,
                                "route_keys": ["GET /market-data"],
                            },
                            "broker_fault": {
                                "faults": {"1": "occupied_port"},
                                "real_entrypoint": "semantic_child.py",
                            },
                            "workflow_switch": {
                                "from_workflow": "workflow-old",
                                "to_workflow": "workflow-new",
                            },
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    knobs = load_knob_plan(path)[("scenario-a", 1)]

    assert knobs.transform_window is not None
    assert knobs.transform_window.naive.total_calls == 8
    assert knobs.broker_fault is not None
    assert knobs.broker_fault.fault_for_attempt(1) is BrokerFaultShape.OCCUPIED_PORT
    assert knobs.workflow_switch == WorkflowSwitchPlan("workflow-old", "workflow-new")


def test_occupied_port_shim_has_no_stderr_and_attempt_two_delegates(tmp_path: Path) -> None:
    real = tmp_path / "real-child.py"
    real.write_text(
        "import socket, sys\n"
        "port = int(sys.argv[sys.argv.index('--port') + 1])\n"
        "sock = socket.socket()\n"
        "try:\n"
        "    sock.bind(('127.0.0.1', port))\n"
        "except OSError:\n"
        "    raise SystemExit(41)\n"
        "else:\n"
        "    raise SystemExit(0)\n",
        encoding="utf-8",
    )
    plan = BrokerFaultPlan({1: BrokerFaultShape.OCCUPIED_PORT}, real_entrypoint=real)

    def available_port() -> int:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
        sock.close()
        return port

    def run(attempt: int) -> subprocess.CompletedProcess[bytes]:
        environment = dict(plan.environment_for_attempt(attempt))
        return subprocess.run(
            [sys.executable, str(broker_entrypoint_path()), "--port", str(available_port())],
            env={**environment, "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            check=False,
            timeout=5,
        )

    first, second, repeat_first, repeat_second = (run(attempt) for attempt in (1, 2, 1, 2))
    assert first.returncode == 41
    assert first.stderr == b""
    assert second.returncode == 0
    assert repeat_first.returncode == first.returncode
    assert repeat_second.returncode == second.returncode


class _FakeTransport:
    def __init__(self, name: str, events: list[str]) -> None:
        self.name = name
        self.events = events

    def cleanup(self) -> None:
        self.events.append(f"{self.name}.cleanup")

    def start(self) -> None:
        self.events.append(f"{self.name}.start")


def test_restart_switch_stops_before_start_and_records_endpoint() -> None:
    events: list[str] = []
    old = _FakeTransport("old", events)
    plan = WorkflowSwitchPlan("workflow-old", "workflow-new")

    replacement, evidence = script_restart_and_switch(
        old,
        plan,
        restart=lambda workflow: _FakeTransport(workflow, events),
        first_call=lambda transport, workflow: (
            events.append(f"{transport.name}.call")
            or EndpointObservation(workflow, workflow, "endpoint-new")
        ),
        stale_endpoint="endpoint-old",
    )

    assert replacement.name == "workflow-new"
    assert events == ["old.cleanup", "workflow-new.start", "workflow-new.call"]
    assert evidence.to_dict() == {
        "from_workflow": "workflow-old",
        "to_workflow": "workflow-new",
        "answered_workflow": "workflow-new",
        "answered_endpoint": "endpoint-new",
        "stale_endpoint_rejected": True,
    }


def test_environment_manifest_pins_active_knobs(tmp_path: Path) -> None:
    from dp_scenarios.operator import OperatorScript
    from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping
    from dp_scenarios.operator.persona import load_persona

    sheet = answer_sheet_from_mapping(
        {
            "version": 1,
            "scenario_id": "knob-manifest",
            "opening_message": "Improve visibility.",
            "turns": ["Improve visibility."],
            "source_answers": {"source": "Use the source."},
            "decision_answers": {"choice": {"terms": ["choice"], "answer": "Yes."}},
            "status_answers": {"status": "Ready."},
            "opening_forbidden_terms": ["source"],
            "open_decision_markers": ["[DECISION NEEDED]"],
            "obstacle_terms": [],
        }
    )
    @dataclass(frozen=True)
    class FixtureScenario:
        package_dir: Path
        id: str
        tier: str
        seed: int
        turn_budget: int
        script: OperatorScript
        dataset: str = "zero_row_optional"
        epochs: int = 1
        repeatability_tier: str = "demonstrated-once"

        @property
        def script_hash(self) -> str:
            from dp_scenarios.operator import operator_script_hash

            return operator_script_hash(self.script)

        def generate_fixture(self, out_dir: Path):
            from dp_scenarios.synthgen import generate_dataset

            return generate_dataset(self.dataset, self.seed, out_dir)

    scenario = FixtureScenario(
        ROOT,
        "knob-manifest",
        "smoke",
        29,
        1,
        OperatorScript.from_components(
            load_persona(ROOT / "scenarios/_personas/smoke.yaml"),
            sheet,
            turns=sheet.turns,
            turn_budget=1,
            phase_by_turn={1: 1},
        ),
    )
    sizing = TransformWindowSizing.from_plans(
        PlanShape("naive", 8),
        PlanShape("bounded", 1),
        per_call_latency_ms=5,
        route_keys=("GET /market-data",),
    )
    with RunEnvironment(
        scenario,
        PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1"),
        root=tmp_path,
        route_config=ROOT / "scenarios/_examples/mockrest.yaml",
        knobs=SupervisorKnobs(
            transform_window=sizing,
            workflow_switch=WorkflowSwitchPlan("workflow-old", "workflow-new"),
        ),
    ) as environment:
        assert environment.manifest.runtime_knobs["transform_window"]["arithmetic"]["bounds_hold"] is True  # type: ignore[index]
        assert environment.manifest.runtime_knobs["workflow_switch"]["enabled"] is True  # type: ignore[index]
        assert environment.mock_source is not None
        routes = environment.mock_source.config.routes  # type: ignore[union-attr]
        assert next(route for route in routes if route.path == "/market-data").latency_ms == 5
        environment.record_workflow_switch(
            WorkflowSwitchEvidence(
                "workflow-old",
                "workflow-new",
                "workflow-new",
                "endpoint-new",
                True,
            )
        )
        assert environment.ledger.read()[-1]["claim"]["answered_endpoint"] == "endpoint-new"  # type: ignore[index]
