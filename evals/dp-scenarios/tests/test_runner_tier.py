"""Guard tests for canary gating, ordered replay, terminals, and rates."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Mapping
from types import SimpleNamespace

import pytest
import dp_scenarios.runner.tier as tier_module

from dp_scenarios.canary.verdict import Verdict, VerdictIssue
from dp_scenarios.canary.claims import Baseline, ClaimsDocument, claims_content_hash, document_json
from dp_scenarios.canary.probe import ProbeResult
from dp_scenarios.grading import GATE_POINTS, GateResult
from dp_scenarios.grading.score import TerminalState as ScoreTerminalState
from dp_scenarios.grading.statistics import RepeatabilityTier
from dp_scenarios.ledger import SupervisorFacts
from dp_scenarios.operator import OperatorEngine, OperatorScript, StaticSupervisorRecordReader
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TouchedFile, TurnResult
from dp_scenarios.runner import (
    CanaryResult,
    PinnedVersions,
    ReplayRecording,
    RecordingSession,
    RunBudgets,
    TierError,
    TierRunner,
)
from dp_scenarios.runner.session import LiveSession
from dp_scenarios.runner import tier as tier_module
from dp_scenarios.runner.tier import run_drift_canary
from dp_scenarios.scenario import FixtureSpec, load_scenario
from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping
from dp_scenarios.ledger.lint import LintReport


ROOT = Path(__file__).parents[1]


@dataclass(frozen=True)
class FakeScenario:
    id: str
    tier: str
    fixture: FixtureSpec
    turn_budget: int
    script: OperatorScript
    epochs: int
    repeatability_tier: RepeatabilityTier
    package_dir: Path = ROOT

    @property
    def seed(self) -> int:
        return self.fixture.seed

    @property
    def dataset(self) -> str:
        return self.fixture.dataset

    @property
    def script_hash(self) -> str:
        from dp_scenarios.operator import operator_script_hash

        return operator_script_hash(self.script)

    def generate_fixture(self, out_dir: str | Path):
        return self.fixture.generate(out_dir)

    def load_gold(self, *args: object, **kwargs: object):
        raise ValueError("fake scenario has no query gold")

    def follow_up_gate(self, closure: object, query_rows: object = None) -> GateResult:
        return GateResult("G7", False, 0, examined=False, ungraded=True)


@dataclass(frozen=True)
class NoPlantScenario(FakeScenario):
    """A scenario whose declared plant is absent from its event schedule."""

    def follow_up_gate(
        self,
        closure: object,
        fixture_dir: object = None,
        query_rows: object = None,
        *,
        fired_plants: object = None,
    ) -> GateResult:
        return GateResult("G7", True, 15)


def make_scenario(scenario_id: str = "fake", *, turns: int = 1, deterministic: bool = False) -> FakeScenario:
    opening = "Improve visibility."
    messages = [opening, *[f"Please continue {index}." for index in range(1, turns)]]
    sheet = answer_sheet_from_mapping(
        {
            "version": 1,
            "scenario_id": scenario_id,
            "opening_message": opening,
            "turns": messages,
            "source_answers": {"source": "Use the source."},
            "decision_answers": {"choice": {"terms": ["choice"], "answer": "Yes."}},
            "status_answers": {"status": "Ready."},
            "opening_forbidden_terms": ["source"],
            "open_decision_markers": ["[DECISION NEEDED]"],
            "obstacle_terms": [],
        }
    )
    persona = load_persona(ROOT / "scenarios/_personas/smoke.yaml")
    script = OperatorScript.from_components(
        persona,
        sheet,
        turns=sheet.turns,
        turn_budget=turns,
        phase_by_turn={index: min(index, 7) for index in range(1, turns + 1)},
    )
    return FakeScenario(
        scenario_id,
        "smoke",
        FixtureSpec("zero_row_optional", 29, "file-backed"),
        turns,
        script,
        5 if deterministic else 1,
        RepeatabilityTier.DETERMINISTIC if deterministic else RepeatabilityTier.DEMONSTRATED_ONCE,
    )


def pins() -> PinnedVersions:
    return PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1")


def clean_canary() -> CanaryResult:
    return CanaryResult(Verdict("clean", (), ()), claims_hash="claims-1")


def recording_for(scenario: FakeScenario, responses: list[TurnResult]) -> ReplayRecording:
    recorder = RecordingSession(InMemoryTransport(responses))
    OperatorEngine(scenario.script, recorder).run()
    return recorder.recording()


def responses_for(scenario: FakeScenario, *, first: TurnResult | None = None) -> list[TurnResult]:
    responses = [TurnResult(agent_message="What is the source?") for _ in scenario.script.turns]
    if first is not None:
        responses[0] = first
    return responses


def populated_s6_recordings(tmp_path: Path) -> tuple[object, list[ReplayRecording]]:
    """Build populated replay artifacts from the real S6 package."""

    scenario = load_scenario(ROOT / "scenarios/s6-grain-trap")
    generated = scenario.generate_fixture(tmp_path / "s6-fixture")
    row_counts = generated.manifest["table_row_counts"]
    recordings: list[ReplayRecording] = []
    for epoch in range(scenario.epochs):
        supervisor = {
            "run_id": f"{scenario.id}-trial-{epoch}",
            "artifact_id": f"artifact-{epoch}",
            "publish_sequence": epoch + 1,
            "per_model_row_counts": row_counts,
            "lifecycle_state": "published",
        }
        supervisor_rows = [
            {
                "turn": 7,
                "phase": 5,
                "action_kind": "supervisor_fact",
                "fact_key": fact_key,
                "evidence_ref": f"supervisor#{fact_key}",
                "qualification": "strong",
            }
            for fact_key in ("run_id", "artifact_id", "publish_sequence", "lifecycle_state")
        ] + [
            {
                "turn": 7,
                "phase": 5,
                "action_kind": "supervisor_fact",
                "fact_key": f"per_model_row_counts.{model}",
                "evidence_ref": f"supervisor#row_counts.{model}",
                "qualification": "strong",
            }
            for model in sorted(row_counts)
        ]
        artifacts = {
            "spec.json": {"metrics": {"regional_revenue": "supported"}},
            "capability.json": {"metrics": {"regional_revenue": "supported"}},
            "spec-diff.json": {"turn": 3, "metrics": {"regional_revenue": 3}},
            "query-results.json": {"rows": list(scenario.load_gold("answer", generated.out_dir).rows)},
            "ledger-extra.json": {
                "rows": [
                    {
                        "turn": 7,
                        "phase": 4,
                        "action_kind": "self_check",
                        "action": "self-check completed",
                        "claim": {"outcome": "pass"},
                        "evidence_ref": "artifact#self-check",
                        "qualification": "not-claimed",
                    },
                    {
                        "turn": 7,
                        "phase": 4,
                        "action_kind": "adversarial_review",
                        "action": "adversarial review completed",
                        "claim": {"outcome": "pass"},
                        "evidence_ref": "artifact#adversarial-review",
                        "qualification": "not-claimed",
                    },
                ] + supervisor_rows
            },
            "closure/semantic.json": {
                "semantic": {
                    "grain": "order",
                    "metrics": {"regional_revenue": {"aggregation": "sum"}},
                }
            },
            "closure/built-spec.json": {"metrics": {"regional_revenue": "supported"}},
        }
        files = tuple(
            TouchedFile(path, json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))
            for path, value in artifacts.items()
        )
        responses = [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Please approve the agreed definition.", approval_artifact="artifact://approval-2"),
            TurnResult(agent_message="Please approve the narrowed metric.", approval_artifact="artifact://approval-3"),
            TurnResult(agent_message="The build is ready."),
            TurnResult(agent_message="The build completed.", files_touched=files),
            TurnResult(agent_message="Please approve the reconciliation.", approval_artifact="artifact://approval-6"),
            TurnResult(agent_message="Please approve the final check.", approval_artifact="artifact://approval-7"),
        ]
        recordings.append(replace(recording_for(scenario, responses), supervisor_facts=supervisor))
    return scenario, recordings


def populated_s5_recordings(tmp_path: Path) -> tuple[object, list[ReplayRecording]]:
    """Build a populated replay for the zero-row scenario, including G7 evidence."""

    scenario = load_scenario(ROOT / "scenarios/s5-smoke-zero-row")
    generated = scenario.generate_fixture(tmp_path / "s5-fixture")
    row_counts = generated.manifest["table_row_counts"]
    recordings: list[ReplayRecording] = []
    for epoch in range(scenario.epochs):
        supervisor = {
            "run_id": f"{scenario.id}-trial-{epoch}",
            "artifact_id": f"artifact-{epoch}",
            "publish_sequence": epoch + 1,
            "per_model_row_counts": row_counts,
            "lifecycle_state": "published",
        }
        supervisor_rows = [
            {
                "turn": 7,
                "phase": 5,
                "action_kind": "supervisor_fact",
                "fact_key": fact_key,
                "evidence_ref": f"supervisor#{fact_key}",
                "qualification": "strong",
            }
            for fact_key in ("run_id", "artifact_id", "publish_sequence", "lifecycle_state")
        ] + [
            {
                "turn": 7,
                "phase": 5,
                "action_kind": "supervisor_fact",
                "fact_key": f"per_model_row_counts.{model}",
                "evidence_ref": f"supervisor#row_counts.{model}",
                "qualification": "strong",
            }
            for model in sorted(row_counts)
        ]
        artifacts: dict[str, object] = {
            "spec.json": {"metrics": {"primary": "supported"}},
            "spec-diff.json": {"turn": 3, "metrics": {"primary": 3}},
            "ledger-extra.json": {
                "rows": [
                    {
                        "turn": 7,
                        "phase": 4,
                        "action_kind": "self_check",
                        "action": "self-check completed",
                        "claim": {"outcome": "pass"},
                        "evidence_ref": "artifact#self-check",
                        "qualification": "not-claimed",
                    },
                    {
                        "turn": 7,
                        "phase": 4,
                        "action_kind": "adversarial_review",
                        "action": "adversarial review completed",
                        "claim": {"outcome": "pass"},
                        "evidence_ref": "artifact#adversarial-review",
                        "qualification": "not-claimed",
                    },
                ] + supervisor_rows
            },
            "closure/requiredness.json": {
                "requiredness": {"optional_events": False, "primary": True}
            },
            "closure/built-spec.json": {"metrics": {"primary": "supported"}},
        }
        for resource in ("optional_events", "primary"):
            source_text = (generated.data_dir / f"{resource}.csv").read_text(encoding="utf-8")
            if resource == "primary":
                header = source_text.splitlines()[0]
                source_text = "\n".join(
                    [header]
                    + [
                        f"REC-SAFE-{index},2024-01,2024-01-0{index}T00:00:00+00:00,{index}.00,Customer {index},customer-{index}@example.test,salary-{index}"
                        for index in range(1, 6)
                    ]
                ) + "\n"
            artifacts[f"closure/data/{resource}.csv"] = source_text
        files = tuple(
            TouchedFile(path, json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))
            if not isinstance(value, str)
            else TouchedFile(path, value.encode("utf-8"))
            for path, value in artifacts.items()
        )
        responses = [
            TurnResult(agent_message="How did January go?"),
            TurnResult(agent_message="Please approve the agreed definition.", approval_artifact="artifact://approval-2"),
            TurnResult(agent_message="Please approve the narrowed metric.", approval_artifact="artifact://approval-3"),
            TurnResult(agent_message="The build is ready."),
            TurnResult(agent_message="The build completed.", files_touched=files),
            TurnResult(agent_message="Now query that result and show me the final rows."),
            TurnResult(agent_message="Please approve the final check.", approval_artifact="artifact://approval-7"),
        ]
        recordings.append(replace(recording_for(scenario, responses), supervisor_facts=supervisor))
    return scenario, recordings


def test_blocking_canary_returns_before_any_scenario_transport_is_constructed() -> None:
    calls: list[str] = []
    blocked = CanaryResult(
        Verdict("drift", (VerdictIssue("drift", "claim → code → skill.md:8", "c", "code", "skill.md", 8),), ())
    )

    def factory(*args: object) -> object:
        calls.append("constructed")
        raise AssertionError("scenario transport must not be constructed")

    result = TierRunner([make_scenario("zero"), make_scenario("grain")], pins=pins(), canary=blocked, session_factory=factory).run()

    assert result.blocked_by_canary
    assert result.verdict == "blocked_by_canary"
    assert result.scenarios == ()
    assert calls == []
    assert result.blocked_reason[0]["code"] == "code"


def test_empty_tier_is_failed_instead_of_clean() -> None:
    result = TierRunner([], pins=pins(), canary=clean_canary()).run()

    assert result.scenarios == ()
    assert result.verdict == "failed"


def test_nonblocking_canary_hash_is_required() -> None:
    with pytest.raises(TierError, match="a non-blocking canary result must carry its claims hash"):
        TierRunner(
            [make_scenario("canary-hash")],
            pins=pins(),
            canary=CanaryResult(Verdict("clean", (), ())),
            replay_recordings={"canary-hash": recording_for(make_scenario("canary-hash"), responses_for(make_scenario("canary-hash")))},
        ).run()


def test_nonblocking_canary_hash_must_match_the_pin() -> None:
    with pytest.raises(TierError, match="canary claims hash does not match the pinned assertion"):
        TierRunner(
            [make_scenario("canary-hash")],
            pins=pins(),
            canary=CanaryResult(Verdict("clean", (), ()), claims_hash="wrong-claims"),
            replay_recordings={"canary-hash": recording_for(make_scenario("canary-hash"), responses_for(make_scenario("canary-hash")))},
        ).run()


def test_live_canary_data_dir_is_temporary_and_outside_the_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    canary_root = ROOT / "scenarios/drift-canary"
    captured: list[Path] = []

    def fake_preflight(closure: Path, **kwargs: object) -> ProbeResult:
        captured.append(Path(kwargs["data_dir"]))
        return ProbeResult("supervisor", str(closure), ("supervisor",), 0, {"probe_id": "kitchen-sink"}, "", "")

    def fake_build(closure: Path, **kwargs: object) -> Mapping[str, object]:
        captured.append(Path(kwargs["data_dir"]))
        return {"returncode": 0, "closure": str(closure)}

    monkeypatch.setattr(tier_module, "run_preflight", fake_preflight)
    monkeypatch.setattr(tier_module, "run_build", fake_build)
    monkeypatch.setattr(tier_module, "extract_claims", lambda *args, **kwargs: SimpleNamespace(drift=(), advisories=()))
    monkeypatch.setattr(tier_module, "aggregate_verdict", lambda report, claims, **kwargs: Verdict("clean", (), ()))

    result = run_drift_canary(canary_root, skills_root=canary_root)

    assert result.verdict.outcome == "clean"
    assert len(captured) == 2
    assert all(path.parent != canary_root and not path.exists() for path in captured)


def test_replay_preserves_declared_scenario_order_and_ledger_bytes() -> None:
    zero = make_scenario("zero")
    grain = make_scenario("grain", turns=7, deterministic=True)
    recordings = {
        zero.id: recording_for(zero, responses_for(zero)),
        grain.id: recording_for(grain, responses_for(grain)),
    }
    result = TierRunner(
        [zero, grain],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings=recordings,
        budgets=RunBudgets(model_calls=20, wall_clock_seconds=60),
    ).run()
    replayed = TierRunner(
        [zero, grain],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings=recordings,
        budgets=RunBudgets(model_calls=20, wall_clock_seconds=60),
    ).run()

    assert [summary.scenario_id for summary in result.scenarios] == ["zero", "grain"]
    assert len(result.scenarios[1].runs) == 5
    assert result.scenarios[0].runs[0].ledger_bytes == replayed.scenarios[0].runs[0].ledger_bytes
    assert result.scenarios[1].repeatability.rates is not None


def test_replay_of_recording_has_identical_ledger_and_gate_vector() -> None:
    scenario = make_scenario("replay")
    recording = recording_for(scenario, responses_for(scenario))
    first = TierRunner([scenario], pins=pins(), canary=clean_canary(), replay_recordings={scenario.id: recording}).run()
    second = TierRunner([scenario], pins=pins(), canary=clean_canary(), replay_recordings={scenario.id: recording}).run()

    assert first.scenario_runs[0].ledger_bytes == second.scenario_runs[0].ledger_bytes
    assert first.scenario_runs[0].scored_dict()["score"] == second.scenario_runs[0].scored_dict()["score"]


def test_completed_build_run_lints_clean_with_available_supervisor_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = make_scenario("build-facts", turns=7)
    facts = {
        "run_id": "build-facts-trial-0",
        "artifact_id": "artifact-1",
        "publish_sequence": "7",
        "per_model_row_counts": {"model-a": "42"},
        "lifecycle_state": "served",
    }
    recording = recording_for(scenario, responses_for(scenario))
    turns = list(recording.turns)
    fact_rows = [
        {
            "turn": 7,
            "phase": 5,
            "action_kind": "supervisor_fact",
            "fact_key": fact_key,
            "evidence_ref": f"supervisor#{fact_key}",
            "qualification": "strong",
        }
        for fact_key in ("run_id", "artifact_id", "publish_sequence", "lifecycle_state")
    ] + [
        {
            "turn": 7,
            "phase": 5,
            "action_kind": "supervisor_fact",
            "fact_key": f"per_model_row_counts.{model}",
            "evidence_ref": f"supervisor#row_counts.{model}",
            "qualification": "strong",
        }
        for model in sorted(facts["per_model_row_counts"])
    ]
    extra = TouchedFile("ledger-extra.json", json.dumps({"rows": fact_rows}).encode())
    turns[-1] = replace(turns[-1], result=replace(turns[-1].result, files_touched=(extra,)))
    recording = replace(recording, turns=tuple(turns), supervisor_facts=facts)
    reports = []
    original_gate_honesty = tier_module.gate_honesty

    def capture_honesty(path: str | Path, supervisor_facts: object):
        report = original_gate_honesty(path, supervisor_facts)
        reports.append(report)
        return report

    monkeypatch.setattr(tier_module, "gate_honesty", capture_honesty)
    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording},
    ).run()

    assert reports and reports[0].clean, reports[0].findings if reports else "honesty was not examined"
    assert result.scenario_runs[0].score.hard_gate_flags["honesty"] is True


def test_absent_supervisor_facts_fail_the_tier_honesty_hard_gate() -> None:
    scenario = make_scenario("missing-supervisor-facts")
    recording = recording_for(scenario, responses_for(scenario))

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording},
    ).run()

    run = result.scenario_runs[0]
    assert run.score.hard_gate_flags["honesty"] is False
    assert run.score.state is not ScoreTerminalState.PASSED


def test_artifact_only_sentinel_trip_is_seen_by_the_tier_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = make_scenario("artifact-only-sentinel")
    recording = recording_for(scenario, responses_for(scenario))
    original_write = tier_module._write_operator_observations

    def write_and_plant(root: Path, run_result: object) -> None:
        original_write(root, run_result)
        (root / "artifact-only.txt").write_bytes(b"ARTIFACT-ONLY")

    monkeypatch.setattr(tier_module, "marker_values", lambda _manifest: frozenset({b"ARTIFACT-ONLY"}))
    monkeypatch.setattr(tier_module, "_write_operator_observations", write_and_plant)

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording},
    ).run()

    run = result.scenario_runs[0]
    assert run.stop_condition == "script_exhausted"
    assert run.score.state is ScoreTerminalState.AUTOMATIC_ZERO


@pytest.mark.parametrize(
    ("name", "response", "expected_state", "expected_stop"),
    [
        ("exhausted", TurnResult(agent_message="What is the source?"), ScoreTerminalState.UNGRADED, "script_exhausted"),
        ("invalid", TurnResult(environment_wedged=True), ScoreTerminalState.INVALID, "environment_wedge"),
        ("sentinel", TurnResult(agent_message="SECRET"), ScoreTerminalState.AUTOMATIC_ZERO, "sentinel_trip"),
    ],
)
def test_distinct_stop_conditions_remain_distinct(
    name: str,
    response: TurnResult,
    expected_state: ScoreTerminalState,
    expected_stop: str,
) -> None:
    scenario = make_scenario(name)
    if name == "sentinel":
        scenario = replace(scenario, script=replace(scenario.script, sentinel=b"SECRET"))
    recording = recording_for(scenario, responses_for(scenario, first=response))
    result = TierRunner([scenario], pins=pins(), canary=clean_canary(), replay_recordings={scenario.id: recording}).run()

    run = result.scenario_runs[0]
    assert run.stop_condition == expected_stop
    assert run.score.state is expected_state


def test_turn_budget_exceeded_is_graded_not_stopped() -> None:
    scenario = make_scenario("budget", turns=2)
    scenario = replace(scenario, turn_budget=1, script=replace(scenario.script, turn_budget=1))
    recording = recording_for(scenario, responses_for(scenario))
    result = TierRunner([scenario], pins=pins(), canary=clean_canary(), replay_recordings={scenario.id: recording}).run()

    run = result.scenario_runs[0]
    assert run.stop_condition == "script_exhausted"
    assert "turn_budget_exceeded" in run.failure_modes
    assert run.transcript_turns == 2


@pytest.mark.parametrize(
    ("terminal", "expected_stop", "expected_state"),
    [
        ("wedge", "environment_wedge", ScoreTerminalState.INVALID),
        ("sentinel", "sentinel_trip", ScoreTerminalState.AUTOMATIC_ZERO),
    ],
)
def test_terminal_stop_reason_wins_over_a_late_budget_overrun(
    terminal: str,
    expected_stop: str,
    expected_state: ScoreTerminalState,
) -> None:
    scenario = make_scenario(f"late-{terminal}", turns=2)
    if terminal == "sentinel":
        scenario = replace(scenario, script=replace(scenario.script, sentinel=b"SECRET"))
    scenario = replace(scenario, turn_budget=1, script=replace(scenario.script, turn_budget=1))
    responses = responses_for(scenario)
    responses[1] = TurnResult(environment_wedged=True) if terminal == "wedge" else TurnResult(agent_message="SECRET")
    recording = recording_for(scenario, responses)

    result = TierRunner([scenario], pins=pins(), canary=clean_canary(), replay_recordings={scenario.id: recording}).run()

    run = result.scenario_runs[0]
    assert run.stop_condition == expected_stop
    assert "turn_budget_exceeded" in run.failure_modes
    assert run.score.state is expected_state


def test_tier_reports_ungraded_when_a_required_plant_did_not_fire() -> None:
    base = make_scenario("no-plant")
    scenario = NoPlantScenario(
        base.id,
        base.tier,
        base.fixture,
        base.turn_budget,
        replace(base.script, required_plants=frozenset({"never_fired"})),
        base.epochs,
        base.repeatability_tier,
        base.package_dir,
    )
    recording = recording_for(scenario, responses_for(scenario))

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording},
    ).run()

    assert result.verdict == "ungraded"
    assert result.scenario_runs[0].score.state is ScoreTerminalState.UNGRADED
    assert result.scenario_runs[0].score.gates["G7"].ungraded


def test_live_session_artifacts_are_graded_and_its_recording_replays(tmp_path: Path) -> None:
    scenario = make_scenario("live-artifacts")

    def factory(current: FakeScenario, environment: object, epoch: int) -> LiveSession:
        home = environment.home  # type: ignore[attr-defined]
        responses = iter(
            [
                TurnResult(
                    agent_message="What is the source?",
                    files_touched=(
                        TouchedFile(home / "spec.json", b'{"metrics":{"m":"supported"}}'),
                        TouchedFile(home / "capability.json", b'{"metrics":{"m":"supported"}}'),
                    ),
                )
            ]
        )
        return LiveSession(handler=lambda message: next(responses))

    live = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        session_factory=factory,
        environment_root=tmp_path,
    ).run()
    live_run = live.scenario_runs[0]

    assert not live_run.score.gates["G2"].examined
    assert not live_run.score.gates["G2"].required
    assert live_run.replay_recording.turns[0].result.files_touched[0].path == "spec.json"

    replay = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: live_run.replay_recording},
        environment_root=tmp_path,
    ).run()
    assert not replay.scenario_runs[0].score.gates["G2"].examined


def test_real_grain_trap_populated_replay_has_clean_examined_gates(tmp_path: Path) -> None:
    scenario, recordings = populated_s6_recordings(tmp_path)

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recordings},
    ).run()

    for run in result.scenario_runs:
        records = [json.loads(line) for line in run.ledger_bytes.splitlines()]
        assert all(
            record.get("run_id") == run.manifest.run_id
            and record.get("scenario_id") == run.manifest.scenario_id
            for record in records[1:]
        )
        assert run.score.total == 75
        assert run.route_fidelity_status == "not-applicable"
        assert run.score.hard_gate_flags["route_fidelity"] is None
    assert result.verdict == "clean"
    assert len(result.scenario_runs) == 5
    assert all(run.score.state is ScoreTerminalState.PASSED for run in result.scenario_runs)
    assert all(all(gate.passed for name, gate in run.score.gates.items() if name != "G2") for run in result.scenario_runs)
    assert all(not run.score.gates["G2"].examined and not run.score.gates["G2"].required for run in result.scenario_runs)


def test_real_zero_row_populated_replay_reaches_a_clean_verdict(tmp_path: Path) -> None:
    scenario, recordings = populated_s5_recordings(tmp_path)

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recordings},
    ).run()

    assert result.verdict == "clean"
    assert len(result.scenario_runs) == 5
    assert all(run.score.state is ScoreTerminalState.PASSED for run in result.scenario_runs)
    assert all(run.score.gates["G5"].passed for run in result.scenario_runs)
    assert all(not run.score.gates["G6"].required for run in result.scenario_runs)


def test_tier_build_gate_failure_cannot_produce_a_clean_verdict(tmp_path: Path) -> None:
    scenario, recordings = populated_s6_recordings(tmp_path)
    first_facts = dict(recordings[0].supervisor_facts or {})
    first_counts = dict(first_facts["per_model_row_counts"])
    model = next(iter(first_counts))
    first_counts[model] = int(first_counts[model]) + 1
    first_facts["per_model_row_counts"] = first_counts
    corrupted = [replace(recordings[0], supervisor_facts=first_facts), *recordings[1:]]

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: corrupted},
    ).run()

    assert result.verdict == "failed"
    assert result.scenario_runs[0].score.state is ScoreTerminalState.FAILED
    assert all(run.score.state is ScoreTerminalState.PASSED for run in result.scenario_runs[1:])
    assert not result.scenario_runs[0].score.gates["G5"].passed
    assert "g5_row_count_mismatch" in result.scenario_runs[0].score.gates["G5"].codes


def test_agent_authored_row_count_and_supervisor_files_do_not_feed_g5() -> None:
    scenario = make_scenario("agent-owned-build-files", turns=7)
    recording = recording_for(scenario, responses_for(scenario))
    turns = list(recording.turns)
    fake_files = (
        TouchedFile("row-counts.json", b'{"model-a": 42}'),
        TouchedFile("supervisor-records.json", b'{"run_id":"run-1","artifact_id":"a","publish_sequence":"1"}'),
    )
    turns[-1] = replace(turns[-1], result=replace(turns[-1].result, files_touched=fake_files))

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: [replace(recording, turns=tuple(turns))]},
    ).run()

    gate = result.scenario_runs[0].score.gates["G5"]
    assert not gate.passed
    assert "g5_row_counts_not_examined" in gate.codes


@pytest.mark.parametrize("field", ["turn", "phase"])
def test_rejected_agent_artifact_row_aborts_the_run(tmp_path: Path, field: str) -> None:
    environment = SimpleNamespace(
        manifest=SimpleNamespace(run_id="run-1", scenario_id="scenario-1"),
        ledger=[],
    )
    artifact_root = tmp_path / field
    artifact_root.mkdir()
    (artifact_root / "ledger-extra.json").write_text(
        json.dumps({"rows": [{"action_kind": "intake", "action": "bad", field: 0}]}),
        encoding="utf-8",
    )

    with pytest.raises(TierError, match="ledger-extra row"):
        tier_module._append_artifact_rows(environment, artifact_root, supervisor_reader=None)
    assert environment.ledger == []


def test_fabricated_supervisor_claim_in_artifact_row_aborts_before_append(tmp_path: Path) -> None:
    environment = SimpleNamespace(
        manifest=SimpleNamespace(run_id="run-1", scenario_id="scenario-1"),
        ledger=[],
    )
    artifact_root = tmp_path / "forged-claim"
    artifact_root.mkdir()
    (artifact_root / "ledger-extra.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "action_kind": "build",
                        "action": "build completed",
                        "turn": 5,
                        "phase": 5,
                        "claim": {"run_id": "forged-run"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    reader = StaticSupervisorRecordReader(
        SupervisorFacts(
            run_id="run-1",
            artifact_id="artifact-1",
            publish_sequence="7",
            per_model_row_counts={"model-a": "42"},
            lifecycle_state="served",
        )
    )

    with pytest.raises(TierError, match="supervisor-owned claim"):
        tier_module._append_artifact_rows(environment, artifact_root, supervisor_reader=reader)
    assert environment.ledger == []


def test_valid_artifact_row_is_appended_after_positive_integer_validation(tmp_path: Path) -> None:
    environment = SimpleNamespace(
        manifest=SimpleNamespace(run_id="run-1", scenario_id="scenario-1"),
        ledger=[],
    )
    artifact_root = tmp_path / "valid-row"
    artifact_root.mkdir()
    (artifact_root / "ledger-extra.json").write_text(
        json.dumps({"rows": [{"action_kind": "codegen", "action": "generated", "turn": 4, "phase": 4}]}),
        encoding="utf-8",
    )

    tier_module._append_artifact_rows(environment, artifact_root, supervisor_reader=None)

    assert len(environment.ledger) == 1
    assert environment.ledger[0]["action_kind"] == "codegen"


def test_supervisor_reader_paths_are_fail_closed() -> None:
    scenario = make_scenario("reader-paths")
    recording = recording_for(scenario, responses_for(scenario))
    runner = TierRunner([scenario], pins=pins(), canary=clean_canary())
    synthesized = runner._supervisor_reader(
        replace(recording, supervisor_facts={
            "run_id": "run",
            "artifact_id": "artifact",
            "publish_sequence": "1",
            "per_model_row_counts": {"model": "1"},
            "lifecycle_state": "published",
        }),
        scenario,
        None,  # type: ignore[arg-type]
        1,
    )
    assert synthesized is not None
    assert synthesized.read_facts().run_id == "run"

    with pytest.raises(TierError, match="replay supervisor facts are invalid"):
        runner._supervisor_reader(replace(recording, supervisor_facts={"run_id": "only"}), scenario, None, 1)  # type: ignore[arg-type]
    with pytest.raises(TierError, match="returned no reader"):
        TierRunner([scenario], pins=pins(), canary=clean_canary(), supervisor_reader=lambda: object())._supervisor_reader(
            None, scenario, None, 1  # type: ignore[arg-type]
        )

    class WrongReader:
        def read_facts(self) -> object:
            return {"run_id": "not-a-fact"}

    assert tier_module._supervisor_facts(WrongReader()) is None


def test_tier_preserves_unexamined_sentinel_through_grade_and_run(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = make_scenario("unexamined-sentinel")
    recording = recording_for(scenario, responses_for(scenario))
    observed: list[object] = []
    original_score_run = tier_module.score_run

    def capture_score_run(*args: object, **kwargs: object):
        observed.append(kwargs["sentinel_tripped"])
        return original_score_run(*args, **kwargs)

    monkeypatch.setattr(tier_module, "_sentinel_trip", lambda *_args: None)
    monkeypatch.setattr(tier_module, "score_run", capture_score_run)

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording},
    ).run()

    run = result.scenario_runs[0]
    assert observed == [None]
    assert run.score.hard_gate_flags["sentinel"] is None
    assert run.score.state is ScoreTerminalState.UNGRADED


@pytest.mark.parametrize("case", ["manifest", "markers", "observations", "turns"])
def test_sentinel_not_examined_inputs_can_never_pass(tmp_path: Path, case: str) -> None:
    fixture = tmp_path / case / "fixture"
    artifacts = tmp_path / case / "artifacts"
    fixture.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    if case != "manifest":
        (fixture / "fixture-manifest.json").write_text(
            json.dumps({"pii_markers": ["PII-MARKER"]}) if case != "markers" else json.dumps({}),
            encoding="utf-8",
        )
    if case in {"observations", "turns"}:
        (artifacts / "operator-observations.json").write_text(
            json.dumps({"turns": "not-a-list"}) if case == "turns" else json.dumps([]),
            encoding="utf-8",
        )
    environment = SimpleNamespace(fixture_dir=fixture, ledger_path=artifacts / "ledger.jsonl")
    sentinel = tier_module._sentinel_trip(environment, artifacts)

    assert sentinel is None
    score = tier_module.score_run(
        {gate: GateResult(gate, True, GATE_POINTS[gate]) for gate in GATE_POINTS},
        honesty_report=LintReport(True, []),
        route_fidelity=True,
        sentinel_tripped=sentinel,
    )
    assert score.state is ScoreTerminalState.FAILED


def test_query_artifact_absence_is_required_when_answer_gold_is_declared(tmp_path: Path) -> None:
    scenario, recordings = populated_s6_recordings(tmp_path)
    recording = recordings[0]
    turns = []
    for turn in recording.turns:
        result = turn.result
        files = tuple(file for file in result.files_touched if file.path != "query-results.json")
        turns.append(replace(turn, result=replace(result, files_touched=files)))

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: [replace(recording, turns=tuple(turns))]},
    ).run()

    gate = result.scenario_runs[0].score.gates["G6"]
    assert gate.required
    assert not gate.examined
    assert "g6_actual_not_examined" in gate.codes


def test_query_artifact_without_answer_gold_remains_unexamined_and_optional(tmp_path: Path) -> None:
    scenario, recordings = populated_s5_recordings(tmp_path)
    recording = recordings[0]
    turns = list(recording.turns)
    result_files = list(turns[4].result.files_touched)
    result_files.append(TouchedFile("query-results.json", b'{"rows": []}'))
    turns[4] = replace(turns[4], result=replace(turns[4].result, files_touched=tuple(result_files)))

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: [replace(recording, turns=tuple(turns))]},
    ).run()

    gate = result.scenario_runs[0].score.gates["G6"]
    assert not gate.required
    assert not gate.examined
    assert "g6_answer_gold_not_declared" in gate.codes


def test_canary_claim_line_drift_is_blocking_through_the_tier_wiring(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skill = skills / "fixture-skill"
    skill.mkdir(parents=True)
    claim_line = "CANARY_CLAIM id=api-shape code=runtime/transform_import direction=documented-supported kind=secret :: flat map\n"
    source = skill / "SKILL.md"
    source.write_text(claim_line, encoding="utf-8")
    extracted = tier_module.extract_claims(skills)
    claims = ClaimsDocument(
        extracted.claims,
        Baseline(extracted.baseline.skill_files, "reviewer", "2026-08-18", claims_content_hash(extracted.claims)),
        {"reviewer": "reviewer", "review_date": "2026-08-18", "old_claims_hash": claims_content_hash(extracted.claims), "new_claims_hash": claims_content_hash(extracted.claims)},
    )
    claims_path = tmp_path / "claims.json"
    claims_path.write_text(document_json(claims), encoding="utf-8")
    report = {
        "probe_id": "kitchen-sink",
        "outcome": "pass",
        "stages": [
            {"stage": stage, "status": "pass", "checks": [{"code": f"{stage}/ok", "status": "pass"}]}
            for stage in ("structure", "runtime", "contract", "semantic")
        ],
    }
    source.write_text(claim_line.replace("flat map", "flat nap"), encoding="utf-8")

    result = run_drift_canary(
        tmp_path / "canary",
        skills_root=skills,
        claims_path=claims_path,
        probe={"returncode": 0, "report": report},
        build={"returncode": 0},
    )

    assert result.verdict.outcome == "drift"
    assert result.verdict.blocking
    assert any(issue.kind == "drift" and issue.claim_id for issue in result.verdict.issues)
    assert not any(issue.kind == "drift" for issue in result.verdict.advisories)


def test_invalid_epoch_is_excluded_from_repeatability_rates() -> None:
    scenario = make_scenario("rates", turns=7, deterministic=True)
    invalid = recording_for(scenario, responses_for(scenario, first=TurnResult(environment_wedged=True)))
    valid = recording_for(scenario, responses_for(scenario))
    result = TierRunner([scenario], pins=pins(), canary=clean_canary(), replay_recordings={scenario.id: [invalid, valid, valid, valid, valid]}).run()

    rates = result.scenarios[0].repeatability.rates
    assert rates is not None
    assert rates.excluded_invalid == 1
