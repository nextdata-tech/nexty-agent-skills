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
from dp_scenarios.knobs import EndpointObservation, SupervisorKnobs, WorkflowSwitchPlan
from dp_scenarios.ledger import fixture_dir_hash
from dp_scenarios.operator import (
    DriverOperator,
    EventSchedule,
    OperatorEngine,
    OperatorScript,
    event_from_mapping,
)
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, ToolCall, TouchedFile, TurnResult
from dp_scenarios.runner import (
    CanaryResult,
    PinnedVersions,
    ReplayRecording,
    RecordingSession,
    RunBudgets,
    TierError,
    TierRunner,
)
from dp_scenarios.runner.qualification import QualificationDisposition
from dp_scenarios.runner.session import LiveSession, SessionError
from dp_scenarios.runner.report import machine_report
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
        return GateResult("follow-up", False, 0, examined=False, ungraded=True)


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
        return GateResult("follow-up", True, 15)


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


def driver_pins() -> PinnedVersions:
    return replace(
        pins(),
        driver_model_id="tier-driver",
        driver_sampling_params={"temperature": 0.0},
    )


def clean_canary() -> CanaryResult:
    return CanaryResult(Verdict("clean", (), ()), claims_hash="claims-1")


def test_tier_runner_drives_the_same_operator_factory_on_replay_and_live_paths(tmp_path: Path) -> None:
    base = make_scenario("driver-tier", turns=3)
    sheet = answer_sheet_from_mapping(
        {
            **base.script.answer_sheet.to_mapping(),
            "driver_forbidden_terms": ["grain"],
            "ground_truth": {"grain_fact": {"terms": ["grain"], "fact": "The grain is one row per account."}},
        }
    )
    script = OperatorScript.from_components(
        base.script.persona,
        sheet,
        turns=base.script.turns,
        turn_budget=3,
        phase_by_turn=base.script.phase_by_turn,
    )
    scenario = replace(base, script=script)
    responses = [
        TurnResult(agent_message="What is the source?"),
        TurnResult(agent_message="Status update."),
        TurnResult(agent_message="Done.", reported=True),
    ]

    def make_driver() -> DriverOperator:
        return DriverOperator(lambda _view: "Understood, carry on.", model_id="tier-driver", temperature=0.0)

    recorder = RecordingSession(InMemoryTransport(responses))
    OperatorEngine(script, recorder, driver=make_driver()).run()
    recording = recorder.recording()

    replayed = TierRunner(
        [scenario],
        pins=driver_pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording},
        operator_factory=make_driver,
        evidence_root=tmp_path / "replay-evidence",
    ).run()
    replay_run = replayed.scenario_runs[0]
    replay_observations = json.loads(
        (Path(replay_run.evidence_bundle_dir) / "artifacts" / "operator-observations.json").read_text()
    )
    assert replay_observations["operator_mode"] == "driver"
    assert replay_observations["driver_model_id"] == "tier-driver"
    assert replay_observations["driver_temperature"] == 0.0
    assert replay_observations["driver_leading_rejected_count"] == 0
    assert replay_observations["driver_obstacle_rejected_count"] == 0
    assert replay_observations["driver_repeat_rejected_count"] == 0
    assert replay_observations["driver_beat_substituted_count"] == 0
    # Turn 1 is never authorable, so no term is in force there; the two
    # authorable turns each carry the one declared driver-forbidden term.
    assert [turn["driver_forbidden_terms_in_force"] for turn in replay_observations["turns"]] == [0, 1, 1]
    assert [turn["driver_skip_reason"] for turn in replay_observations["turns"]] == ["turn_one", None, None]
    assert replay_run.qualification.operator_mode == "driver"

    (tmp_path / "live-env").mkdir()
    live = TierRunner(
        [scenario],
        pins=driver_pins(),
        canary=clean_canary(),
        session_factory=lambda *_args: InMemoryTransport(responses),
        operator_factory=make_driver,
        environment_root=tmp_path / "live-env",
        evidence_root=tmp_path / "live-evidence",
    ).run()
    live_run = live.scenario_runs[0]
    live_observations = json.loads(
        (Path(live_run.evidence_bundle_dir) / "artifacts" / "operator-observations.json").read_text()
    )
    assert live_observations["operator_mode"] == "driver"
    assert [turn["operator_mode"] for turn in live_observations["turns"]] == ["scripted", "driver", "driver"]

    rejected_text = "REJECTED-DRIVER-TEXT-GRAIN"
    def rejecting_driver() -> DriverOperator:
        return DriverOperator(
            lambda _view: rejected_text,
            model_id="tier-driver",
            temperature=0.0,
        )
    rejected_recorder = RecordingSession(InMemoryTransport(responses))
    OperatorEngine(script, rejected_recorder, driver=rejecting_driver()).run()
    rejected_recording = rejected_recorder.recording()
    rejected = TierRunner(
        [scenario],
        pins=driver_pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: rejected_recording},
        operator_factory=rejecting_driver,
        evidence_root=tmp_path / "rejected-evidence",
    ).run()
    rejected_bundle = Path(rejected.scenario_runs[0].evidence_bundle_dir)
    rejected_observations = json.loads(
        (rejected_bundle / "artifacts" / "operator-observations.json").read_text()
    )
    # Without this the containment assertion below would hold vacuously: it
    # must be a run in which the driver text really was rejected.
    assert rejected_observations["driver_leading_rejected_count"] == 2
    assert all(
        rejected_text not in path.read_text(encoding="utf-8", errors="replace")
        for path in rejected_bundle.rglob("*")
        if path.is_file()
    )

    scripted = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording_for(scenario, responses)},
        evidence_root=tmp_path / "scripted-evidence",
    ).run()
    scripted_observations = json.loads(
        (Path(scripted.scenario_runs[0].evidence_bundle_dir) / "artifacts" / "operator-observations.json").read_text()
    )
    assert scripted_observations["operator_mode"] == "scripted"
    assert scripted_observations["driver_model_id"] is None
    assert scripted_observations["driver_temperature"] is None
    assert [
        scripted_observations[key]
        for key in (
            "driver_leading_rejected_count",
            "driver_obstacle_rejected_count",
            "driver_repeat_rejected_count",
            "driver_beat_substituted_count",
        )
    ] == [0, 0, 0, 0]
    assert all(turn["driver_skip_reason"] is None for turn in scripted_observations["turns"])


def recording_for(scenario: FakeScenario, responses: list[TurnResult]) -> ReplayRecording:
    recorder = RecordingSession(InMemoryTransport(responses))
    OperatorEngine(scenario.script, recorder).run()
    return recorder.recording()


def responses_for(scenario: FakeScenario, *, first: TurnResult | None = None) -> list[TurnResult]:
    responses = [TurnResult(agent_message="What is the source?") for _ in scenario.script.turns]
    if first is not None:
        responses[0] = first
    return responses


def populated_parent_child_recordings(tmp_path: Path) -> tuple[object, list[ReplayRecording]]:
    """Build populated replay artifacts from the real parent-child-grain-trap package."""

    scenario = load_scenario(ROOT / "scenarios/parent-child-grain-trap")
    generated = scenario.generate_fixture(tmp_path / "parent-child-fixture")
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
        artifacts = {
            "spec.json": {"metrics": {"regional_revenue": "supported"}},
            "capability.json": {"metrics": {"regional_revenue": "supported"}},
            "spec-diff.json": {"turn": 3, "metrics": {"regional_revenue": 3}},
            "query-results.json": {"rows": list(scenario.load_gold("answer", generated.out_dir).rows)},
            "agent-attestations.json": {
                "attestations": [
                    {"action_kind": "self_check", "turn": 5, "outcome": "pass", "evidence_ref": "tool:self-check"},
                    {"action_kind": "adversarial_review", "turn": 5, "outcome": "pass", "evidence_ref": "tool:adversarial-review"},
                ]
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
            TurnResult(
                agent_message="The build completed.",
                tool_calls=(
                    ToolCall("mcp__nxd-desktop__check_data_product", result={"status": "pass"}),
                    ToolCall("Skill", arguments={"skill": "nxd-review-closure"}, result={"status": "pass"}),
                ),
                files_touched=files,
            ),
            TurnResult(agent_message="Please approve the reconciliation.", approval_artifact="artifact://approval-6"),
            TurnResult(agent_message="Please approve the final check.", approval_artifact="artifact://approval-7"),
        ]
        recordings.append(replace(recording_for(scenario, responses), supervisor_facts=supervisor))
    return scenario, recordings


def populated_zero_row_recordings(
    tmp_path: Path, *, opening_agent_message: str | None = None
) -> tuple[object, list[ReplayRecording]]:
    """Build a populated replay for the zero-row scenario, including follow-up evidence.

    ``opening_agent_message`` overrides what the agent says on turn 1. It
    exists so a caller can drive a question the scripted answer bank does not
    cover through the *real* shipped answer sheet; the default preserves the
    original transcript for every other caller.
    """

    scenario = load_scenario(ROOT / "scenarios/zero-row-optional-output")
    generated = scenario.generate_fixture(tmp_path / "zero-row-fixture")
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
        artifacts: dict[str, object] = {
            "spec.json": {"metrics": {"primary": "supported"}},
            "spec-diff.json": {"turn": 3, "metrics": {"primary": 3}},
            "agent-attestations.json": {
                "attestations": [
                    {"action_kind": "self_check", "turn": 5, "outcome": "pass", "evidence_ref": "tool:self-check"},
                    {"action_kind": "adversarial_review", "turn": 5, "outcome": "pass", "evidence_ref": "tool:adversarial-review"},
                ]
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
            TurnResult(agent_message=opening_agent_message or "How did January go?"),
            TurnResult(agent_message="Please approve the agreed definition.", approval_artifact="artifact://approval-2"),
            TurnResult(agent_message="Please approve the narrowed metric.", approval_artifact="artifact://approval-3"),
            TurnResult(agent_message="The build is ready."),
            TurnResult(
                agent_message="The build completed.",
                tool_calls=(
                    ToolCall("mcp__nxd-desktop__check_data_product", result={"status": "pass"}),
                    ToolCall("Skill", arguments={"skill": "nxd-review-closure"}, result={"status": "pass"}),
                ),
                files_touched=files,
            ),
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


def test_tier_retains_a_digestable_evidence_bundle_and_replay_status(tmp_path: Path) -> None:
    scenario = make_scenario("bundle")
    recording = recording_for(scenario, responses_for(scenario))
    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording},
        evidence_root=tmp_path / "evidence",
    ).run()

    run = result.scenario_runs[0]
    bundle = Path(run.evidence_bundle_dir)
    assert run.replay_verification_status == "verified"
    assert run.qualification.disposition.value == "OBSERVED"  # the fake scenario is not fully scoreable
    assert (bundle / "evidence.jsonl").is_file()
    assert (bundle / "oracle").is_dir()
    assert (bundle / "session-replay.json").is_file()
    assert (bundle / "qualification.json").is_file()
    assert (bundle / "bundle.sha256").read_text(encoding="ascii").strip() == run.bundle_digest
    reported = machine_report(result)["scenarios"][0]["runs"][0]
    assert "evidence_bundle_dir" not in reported
    assert reported["bundle_digest"] == run.bundle_digest


def test_tier_does_not_create_hidden_evidence_root_when_retention_is_not_requested() -> None:
    scenario = make_scenario("no-hidden-evidence")
    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording_for(scenario, responses_for(scenario))},
    ).run()

    run = result.scenario_runs[0]
    assert run.evidence_bundle_dir is None
    assert run.bundle_digest is None


def test_tier_rejects_existing_evidence_destination_before_running_a_session(tmp_path: Path) -> None:
    scenario = make_scenario("evidence-collision")
    destination = tmp_path / "evidence" / scenario.id / "epoch-1"
    destination.mkdir(parents=True)
    called: list[str] = []

    def forbidden_session() -> object:
        called.append("constructed")
        raise AssertionError("session must not be constructed after an evidence collision")

    with pytest.raises(TierError, match="evidence bundle destination already exists"):
        TierRunner(
            [scenario],
            pins=pins(),
            canary=clean_canary(),
            session_factory=forbidden_session,
            evidence_root=tmp_path / "evidence",
        ).run()
    assert called == []


def test_malformed_agent_attestation_is_a_grade_finding_not_a_tier_abort(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "agent-attestations.json").write_text(
        '{"attestations":[{"action_kind":"self_check","turn":1,"outcome":"pass","unexpected":true}]}\n',
        encoding="utf-8",
    )

    parsed = tier_module._agent_attestations(artifact_root)

    assert parsed.values == ()
    assert parsed.findings[0].code == "agent_attestations_invalid"

    agent_root = tmp_path / "agent"
    agent_root.mkdir()
    (agent_root / "agent-attestations.json").write_text(
        '{"attestations":[{"action_kind":"self_check","turn":1,"outcome":"pass","evidence_ref":"tool:self-check"}]}\n',
        encoding="utf-8",
    )
    from_agent_workspace = tier_module._agent_attestations(agent_root, fallback_root=artifact_root)
    assert len(from_agent_workspace.values) == 1

    (artifact_root / "agent-attestations.json").write_text(
        '{"attestations":[{"action_kind":"self_check","turn":1,"outcome":"pass"}]}\n',
        encoding="utf-8",
    )
    missing_required_key = tier_module._agent_attestations(artifact_root)
    assert missing_required_key.values == ()
    assert missing_required_key.findings[0].code == "agent_attestations_invalid"


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


def test_a_read_result_does_not_trip_the_sentinel_gate_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression the earlier fix's own tests missed.

    ``_leakable_turn_surfaces`` was unit-tested to exempt a source-tool
    result, but ``_sentinel_trip`` still handed the whole ``artifact_root``
    directory to the scanner as one raw surface -- and
    ``operator-observations.json`` (written under that root, carrying the
    raw, unfiltered tool result) was re-read whole from there, bypassing the
    exemption entirely. This drives a real turn through ``TierRunner.run()``,
    the actual call path, rather than calling ``_leakable_turn_surfaces`` in
    isolation.
    """

    monkeypatch.setattr(tier_module, "marker_values", lambda _manifest: frozenset({b"PII-SENTINEL"}))
    scenario = make_scenario("read-result-sentinel")
    read_turn = TurnResult(
        agent_message="The fixture carries PII columns; I will not expose them.",
        tool_calls=(ToolCall("Read", arguments={"file_path": "fixture/data/primary.csv"}, result={"content": "PII-SENTINEL"}),),
    )
    recording = recording_for(scenario, responses_for(scenario, first=read_turn))

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording},
    ).run()

    run = result.scenario_runs[0]
    assert run.stop_condition == "script_exhausted"
    assert run.score.state is not ScoreTerminalState.AUTOMATIC_ZERO


def test_a_product_tool_result_still_trips_the_sentinel_gate_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The complement: a real leak into a served result is still caught
    through the actual TierRunner.run() call path, not just in isolation."""

    monkeypatch.setattr(tier_module, "marker_values", lambda _manifest: frozenset({b"PII-SENTINEL"}))
    scenario = make_scenario("product-result-sentinel")
    query_turn = TurnResult(
        agent_message="Here are the results.",
        tool_calls=(ToolCall("mcp__nxd-desktop__run_semantic_query", arguments={"sql": "select *"}, result={"rows": [{"email": "PII-SENTINEL"}]}),),
    )
    recording = recording_for(scenario, responses_for(scenario, first=query_turn))

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording},
    ).run()

    run = result.scenario_runs[0]
    assert run.stop_condition == "script_exhausted"
    assert run.score.state is ScoreTerminalState.AUTOMATIC_ZERO


def test_a_written_file_carrying_a_sentinel_trips_the_gate_via_files_touched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A written file's bytes reach the sentinel gate end to end.

    This does not isolate the ``files_touched`` branch of
    ``_leakable_turn_surfaces`` specifically -- ``ReplaySession._materialize``
    also writes the file's bytes to disk under ``artifact_root``, so the
    ordinary raw artifact scan would catch this leak even with that branch
    removed. That branch is pinned in isolation by
    ``test_a_sentinel_in_a_touched_files_content_is_always_a_leak`` instead;
    this test's job is only to confirm the write is caught somewhere along
    the real ``TierRunner.run()`` path.
    """

    monkeypatch.setattr(tier_module, "marker_values", lambda _manifest: frozenset({b"PII-SENTINEL"}))
    scenario = make_scenario("files-touched-sentinel")
    write_turn = TurnResult(
        agent_message="Wrote the closure.",
        files_touched=(TouchedFile("closure/leak.txt", b"PII-SENTINEL"),),
    )
    recording = recording_for(scenario, responses_for(scenario, first=write_turn))

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording},
    ).run()

    run = result.scenario_runs[0]
    assert run.stop_condition == "script_exhausted"
    assert run.score.state is ScoreTerminalState.AUTOMATIC_ZERO


def test_a_read_result_does_not_trip_the_sentinel_gate_on_the_live_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The high-severity gap the review found in the first fix.

    ``session-replay.json`` is only written when the transport is a
    ``RecordingSession`` -- the live path -- never under ``replay_recordings``.
    Every earlier end-to-end sentinel test drives the replay path, so none of
    them could see that ``session-replay.json`` carries the same raw,
    unfiltered tool-call shape as ``operator-observations.json`` and was
    still being read whole by ``_artifacts_surface_bytes``. This drives the
    real ``RecordingSession`` branch via ``session_factory=`` instead.
    """

    monkeypatch.setattr(tier_module, "marker_values", lambda _manifest: frozenset({b"PII-SENTINEL"}))
    scenario = make_scenario("live-read-result-sentinel")
    read_turn = TurnResult(
        agent_message="The fixture carries PII columns; I will not expose them.",
        tool_calls=(ToolCall("Read", arguments={"file_path": "fixture/data/primary.csv"}, result={"content": "PII-SENTINEL"}),),
    )
    responses = responses_for(scenario, first=read_turn)

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        session_factory=lambda *_args: InMemoryTransport(responses),
        environment_root=tmp_path,
    ).run()

    run = result.scenario_runs[0]
    assert run.stop_condition == "script_exhausted"
    assert run.score.state is not ScoreTerminalState.AUTOMATIC_ZERO


def test_a_product_tool_result_still_trips_the_sentinel_gate_on_the_live_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The complement, on the same live path: a real leak into
    session-replay.json is still caught, not just tolerated."""

    monkeypatch.setattr(tier_module, "marker_values", lambda _manifest: frozenset({b"PII-SENTINEL"}))
    scenario = make_scenario("live-product-result-sentinel")
    query_turn = TurnResult(
        agent_message="Here are the results.",
        tool_calls=(ToolCall("mcp__nxd-desktop__run_semantic_query", arguments={"sql": "select *"}, result={"rows": [{"email": "PII-SENTINEL"}]}),),
    )
    responses = responses_for(scenario, first=query_turn)

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        session_factory=lambda *_args: InMemoryTransport(responses),
        environment_root=tmp_path,
    ).run()

    run = result.scenario_runs[0]
    assert run.stop_condition == "script_exhausted"
    assert run.score.state is ScoreTerminalState.AUTOMATIC_ZERO


def test_a_malformed_session_replay_entry_falls_back_to_a_raw_scan(tmp_path: Path) -> None:
    """The medium finding from the second review round.

    A ``turns`` entry that is a mapping without ``"result"`` is not the
    ``RecordedTurn.to_dict`` shape ``session-replay.json`` is supposed to
    have. The extractor must signal that by returning ``None`` -- the same
    way ``_turns_from_operator_observations`` does for its own shape check --
    so ``_artifacts_surface_bytes`` falls back to a raw byte read of the
    whole file instead of silently substituting a partial view that could
    hide a leak sitting under a key the unwrapping doesn't recognise.
    """

    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "session-replay.json").write_text(
        json.dumps({"turns": [{"unexpected_key": "PII-SENTINEL"}]}), encoding="utf-8"
    )

    surface = tier_module._artifacts_surface_bytes(artifact_root)

    assert surface is not None
    assert b"PII-SENTINEL" in surface


def test_turns_from_session_replay_returns_none_on_a_missing_result_key() -> None:
    assert tier_module._turns_from_session_replay({"turns": [{"operator_message": {}}]}) is None


def test_turns_from_session_replay_unwraps_a_well_formed_entry() -> None:
    result = tier_module._turns_from_session_replay(
        {"turns": [{"operator_message": {}, "result": {"agent_message": "hi"}}]}
    )
    assert result == [{"agent_message": "hi"}]


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
    assert result.scenario_runs[0].score.gates["follow-up"].ungraded


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

    assert not live_run.score.gates["capability"].examined
    assert not live_run.score.gates["capability"].required
    assert live_run.replay_recording.turns[0].result.files_touched[0].path == "spec.json"

    replay = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: live_run.replay_recording},
        environment_root=tmp_path,
    ).run()
    assert not replay.scenario_runs[0].score.gates["capability"].examined


def test_tier_preserves_primary_error_when_transport_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingTransport:
        def start_fresh_session(self) -> str:
            return "session-1"

        def send_message(self, message: object) -> TurnResult:
            return TurnResult(agent_message="What is the source?")

        def close(self) -> None:
            raise RuntimeError("transport cleanup failed")

    def fail_run(_engine: OperatorEngine) -> object:
        raise ValueError("evaluation failed")

    monkeypatch.setattr(OperatorEngine, "run", fail_run)

    with pytest.raises(ValueError, match="evaluation failed") as error:
        TierRunner(
            [make_scenario("cleanup-primary")],
            pins=pins(),
            canary=clean_canary(),
            session_factory=lambda: FailingTransport(),
            environment_root=tmp_path,
        ).run()

    assert any("TierRunner transport cleanup failed" in note for note in error.value.__notes__)


def test_composed_runner_applies_epoch_knobs_and_switches_workflow(tmp_path: Path) -> None:
    scenario = make_scenario("composed-knob", turns=2)
    event = event_from_mapping(
        {
            "version": 1,
            "id": "workflow-switch",
            "trigger_turn": 2,
            "type": "back_after_lunch",
            "content": "I am back.",
            "outcome": "workflow switched",
            "gap_seconds": 1,
        }
    )
    scenario = replace(scenario, script=replace(scenario.script, events=EventSchedule((event,))))
    initial = InMemoryTransport(
        [TurnResult(agent_message="What is the source?")]
    )
    replacement = InMemoryTransport(
        [TurnResult(agent_message="What is the source?")]
    )
    transports = iter((initial,))
    restarted: list[str] = []

    def session_factory(current: FakeScenario, environment: object, epoch: int) -> InMemoryTransport:
        return next(transports)

    def restart_factory(
        current: FakeScenario,
        environment: object,
        epoch: int,
        workflow: str,
    ) -> InMemoryTransport:
        restarted.append(workflow)
        return replacement

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        session_factory=session_factory,
        environment_root=tmp_path,
        knob_plan={
            (scenario.id, 1): SupervisorKnobs(
                workflow_switch=WorkflowSwitchPlan("workflow-old", "workflow-new")
            )
        },
        workflow_restart_factory=restart_factory,
        workflow_observer=lambda message, turn, workflow: EndpointObservation(
            workflow,
            workflow,
            "endpoint-new",
        ),
    ).run()

    run = result.scenario_runs[0]
    assert restarted == ["workflow-new"]
    assert initial.started_fresh == ["session-1"]
    assert replacement.started_fresh == ["session-1"]
    assert run.manifest.runtime_knobs["workflow_switch"]["enabled"] is True  # type: ignore[index]
    assert len(run.replay_recording.turns) == 2
    rows = [json.loads(line) for line in run.ledger_bytes.splitlines()]
    switch_rows = [row for row in rows if row.get("evidence_ref") == "runtime-knobs/workflow-switch"]
    assert switch_rows and switch_rows[0]["claim"] == {
        "from_workflow": "workflow-old",
        "to_workflow": "workflow-new",
        "answered_workflow": "workflow-new",
        "answered_endpoint": "endpoint-new",
        "stale_endpoint_rejected": True,
    }


def test_real_grain_trap_populated_replay_has_clean_examined_gates(tmp_path: Path) -> None:
    scenario, recordings = populated_parent_child_recordings(tmp_path)

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
    assert all(all(gate.passed for name, gate in run.score.gates.items() if name != "capability") for run in result.scenario_runs)
    assert all(not run.score.gates["capability"].examined and not run.score.gates["capability"].required for run in result.scenario_runs)


def test_repeatability_certification_promotes_live_run_and_refreshes_bundle(tmp_path: Path) -> None:
    scenario, recordings = populated_parent_child_recordings(tmp_path)
    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recordings},
        evidence_root=tmp_path / "evidence",
    ).run()
    run = result.scenario_runs[0]
    live_manifest = replace(
        run.manifest,
        validation_mode="live",
        supervisor_binary_path="/opt/nxd-desktop-supervisor",
        session_root="/tmp/desktop-session",
        session_config_path="/tmp/desktop-session/mcp-config.json",
        session_config_sha256="sha256:config",
        session_trace_path="/tmp/desktop-session/trace.jsonl",
        session_server_result_path="/tmp/desktop-session/server-result.json",
    )

    promoted = tier_module._promote_certified_run(replace(run, manifest=live_manifest))
    bundle = Path(run.evidence_bundle_dir)

    assert promoted.qualification.disposition is QualificationDisposition.CERTIFIED
    assert promoted.bundle_digest != run.bundle_digest
    assert json.loads((bundle / "qualification.json").read_text(encoding="utf-8"))["disposition"] == "CERTIFIED"
    assert (bundle / "bundle.sha256").read_text(encoding="ascii").strip() == promoted.bundle_digest


def test_real_zero_row_populated_replay_reaches_a_clean_verdict(tmp_path: Path) -> None:
    scenario, recordings = populated_zero_row_recordings(tmp_path)

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recordings},
    ).run()

    assert result.verdict == "clean"
    assert len(result.scenario_runs) == 5
    assert all(run.score.state is ScoreTerminalState.PASSED for run in result.scenario_runs)
    assert all(run.score.gates["build"].passed for run in result.scenario_runs)
    assert all(not run.score.gates["query"].required for run in result.scenario_runs)


def test_tier_build_gate_failure_cannot_produce_a_clean_verdict(tmp_path: Path) -> None:
    scenario, recordings = populated_parent_child_recordings(tmp_path)
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
    assert not result.scenario_runs[0].score.gates["build"].passed
    assert "build_row_count_mismatch" in result.scenario_runs[0].score.gates["build"].codes


def test_agent_authored_row_count_and_supervisor_files_do_not_feed_g5() -> None:
    scenario = make_scenario("agent-owned-build-files", turns=7)
    recording = recording_for(scenario, responses_for(scenario))
    turns = list(recording.turns)
    fake_files = (
        TouchedFile("row-count-oracle.json", b'{"per_model_row_counts": {"model-a": 42}}'),
        TouchedFile("route-fidelity.json", b"true"),
    )
    turns[-1] = replace(turns[-1], result=replace(turns[-1].result, files_touched=fake_files))

    with pytest.raises(SessionError, match="reserved for harness-owned evidence"):
        TierRunner(
            [scenario],
            pins=pins(),
            canary=clean_canary(),
            replay_recordings={scenario.id: [replace(recording, turns=tuple(turns))]},
        ).run()


@pytest.mark.parametrize("field", ["turn", "phase"])
def test_rejected_agent_artifact_row_aborts_the_run(tmp_path: Path, field: str) -> None:
    artifact_root = tmp_path / field
    artifact_root.mkdir()
    (artifact_root / "ledger-extra.json").write_text(
        json.dumps({"rows": [{"action_kind": "intake", "action": "bad", field: 0}]}),
        encoding="utf-8",
    )

    with pytest.raises(TierError, match="agent-owned ledger artifact"):
        tier_module._append_artifact_rows(artifact_root)


def test_fabricated_supervisor_claim_in_artifact_row_aborts_before_append(tmp_path: Path) -> None:
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
    with pytest.raises(TierError, match="agent-owned ledger artifact"):
        tier_module._append_artifact_rows(artifact_root)


def test_agent_artifact_row_is_never_appended(tmp_path: Path) -> None:
    artifact_root = tmp_path / "valid-row"
    artifact_root.mkdir()
    (artifact_root / "ledger-extra.json").write_text(
        json.dumps({"rows": [{"action_kind": "codegen", "action": "generated", "turn": 4, "phase": 4}]}),
        encoding="utf-8",
    )

    with pytest.raises(TierError, match="agent-owned ledger artifact"):
        tier_module._append_artifact_rows(artifact_root)


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


def test_fixture_integrity_is_checked_against_row_zero(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "data.csv").write_text("id\n1\n", encoding="utf-8")
    environment = SimpleNamespace(
        fixture_dir=fixture,
        manifest=SimpleNamespace(fixture_dir_hash=fixture_dir_hash(fixture)),
    )
    assert tier_module._fixture_integrity_error(environment) is None
    (fixture / "data.csv").write_text("id\n2\n", encoding="utf-8")
    assert tier_module._fixture_integrity_error(environment) == (
        "fixture directory changed after row-zero anchoring"
    )


@pytest.mark.parametrize("case", ["manifest", "markers", "observations", "turns"])
def test_sentinel_not_examined_inputs_can_never_pass(tmp_path: Path, case: str) -> None:
    fixture = tmp_path / case / "fixture"
    artifacts = tmp_path / case / "artifacts"
    fixture.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    generated_manifest = {"pii_markers": ["PII-MARKER"]} if case not in {"manifest", "markers"} else {}
    if case in {"observations", "turns"}:
        (artifacts / "operator-observations.json").write_text(
            json.dumps({"turns": "not-a-list"}) if case == "turns" else json.dumps([]),
            encoding="utf-8",
        )
    environment = SimpleNamespace(
        fixture_dir=fixture,
        generated_fixture_manifest=generated_manifest,
        ledger_path=artifacts / "ledger.jsonl",
    )
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
    scenario, recordings = populated_parent_child_recordings(tmp_path)
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

    gate = result.scenario_runs[0].score.gates["query"]
    assert gate.required
    assert not gate.examined
    assert "query_actual_not_examined" in gate.codes


def test_query_artifact_without_answer_gold_remains_unexamined_and_optional(tmp_path: Path) -> None:
    scenario, recordings = populated_zero_row_recordings(tmp_path)
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

    gate = result.scenario_runs[0].score.gates["query"]
    assert not gate.required
    assert not gate.examined
    assert "query_answer_gold_not_declared" in gate.codes


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


# --------------------------------------------------------------------------
# Sentinel surfaces: what counts as a leak, found by the first live run
# --------------------------------------------------------------------------


def _turn(**overrides: object) -> dict[str, object]:
    turn: dict[str, object] = {"turn": 1, "phase": 1, "agent_message": "", "tool_calls": []}
    turn.update(overrides)
    return turn


def test_reading_the_source_fixture_is_not_a_sentinel_leak() -> None:
    """The defect the first live run surfaced.

    The agent Read the fixture CSV, the planted PII came back in the tool
    result, and the whole turn record was scanned -- so inspecting the source
    scored an automatic zero. Inspecting the source is what the intake and
    capability phases require, so this made the correct behaviour unpassable.
    """

    surfaces = tier_module._leakable_turn_surfaces(
        [
            _turn(
                agent_message="primary.csv carries PII columns; I will not expose them.",
                tool_calls=[
                    {
                        "name": "Read",
                        "arguments": {"file_path": "fixture/data/primary.csv"},
                        "result": {"content": "NAME-SENTINEL-abc,salary-sentinel-def"},
                    }
                ],
            )
        ]
    )
    assert "NAME-SENTINEL-abc" not in json.dumps(surfaces)


def test_a_sentinel_in_a_served_query_result_is_still_a_leak() -> None:
    # The complement: PII that survived into the product is exactly what this
    # gate exists to catch, so product-tool results stay scanned.
    surfaces = tier_module._leakable_turn_surfaces(
        [
            _turn(
                tool_calls=[
                    {
                        "name": "mcp__nxd-desktop__run_semantic_query",
                        "arguments": {"sql": "select * from model"},
                        "result": {"rows": [{"customer_email": "NAME-SENTINEL-abc"}]},
                    }
                ]
            )
        ]
    )
    assert "NAME-SENTINEL-abc" in json.dumps(surfaces)


def test_a_sentinel_the_agent_writes_into_a_tool_argument_is_a_leak() -> None:
    # Source-tool *results* are exempt; source-tool *arguments* are not.
    # Writing the sentinel into a file is a leak however the agent got it.
    surfaces = tier_module._leakable_turn_surfaces(
        [
            _turn(
                tool_calls=[
                    {
                        "name": "Write",
                        "arguments": {"file_path": "out.csv", "content": "NAME-SENTINEL-abc"},
                        "result": {"content": "ok"},
                    }
                ]
            )
        ]
    )
    assert "NAME-SENTINEL-abc" in json.dumps(surfaces)


def test_a_sentinel_in_the_agents_own_prose_is_a_leak() -> None:
    surfaces = tier_module._leakable_turn_surfaces([_turn(agent_message="the value is NAME-SENTINEL-abc")])
    assert "NAME-SENTINEL-abc" in json.dumps(surfaces)


def test_a_sentinel_in_a_touched_files_content_is_always_a_leak() -> None:
    # A write is a leak however it happens -- unlike a tool result, there is
    # no source-tool exemption for files_touched.
    surfaces = tier_module._leakable_turn_surfaces(
        [_turn(files_touched=[{"path": "closure/leak.txt", "content": "NAME-SENTINEL-abc"}])]
    )
    assert "NAME-SENTINEL-abc" in json.dumps(surfaces)


def test_a_files_touched_entry_missing_the_content_key_is_scanned_whole() -> None:
    # A mapping without "content" is malformed, not empty: file.get("content")
    # would silently return None and drop whatever the entry actually
    # carries under an unexpected key, so the whole entry is kept instead.
    surfaces = tier_module._leakable_turn_surfaces(
        [_turn(files_touched=[{"path": "closure/leak.txt", "unexpected_key": "NAME-SENTINEL-abc"}])]
    )
    assert "NAME-SENTINEL-abc" in json.dumps(surfaces)


def test_transcript_delta_keeps_every_line_of_a_multi_line_assistant_block() -> None:
    """The medium finding: a per-line prefix filter only keeps a block's
    first line, since the [assistant]/[tool_use:]/[tool_result] prefix marks
    the whole block, not each of its internal lines. The agent's own prose is
    the "always leakable" category, so a sentinel on any line of a multi-line
    block must survive, not just one on the first line."""

    delta = (
        "[assistant] Scanning the owner column.\n"
        "Values look like NAME-SENTINEL-abc -- I will not carry these forward.\n"
        "[tool_result] \"unrelated result\""
    )
    surfaces = tier_module._leakable_turn_surfaces([_turn(transcript_delta=delta)])
    assert "NAME-SENTINEL-abc" in json.dumps(surfaces)


def test_transcript_delta_drops_every_line_of_a_multi_line_tool_result_block() -> None:
    # The complement: a multi-line [tool_result] block's continuation lines
    # must stay dropped too, not just its first line.
    delta = (
        "[assistant] Reading the source.\n"
        "[tool_use:Read] {}\n"
        '[tool_result] "line one of the result\n'
        'NAME-SENTINEL-abc is line two"'
    )
    surfaces = tier_module._leakable_turn_surfaces([_turn(transcript_delta=delta)])
    assert "NAME-SENTINEL-abc" not in json.dumps(surfaces)


def test_transcript_delta_keeps_assistant_and_tool_use_lines_but_drops_tool_result_lines() -> None:
    """The line-prefix filter added alongside the artifacts-surface fix.

    A [tool_result] line in transcript_delta does not itself name which tool
    produced it, unlike the structured tool_calls list, so it cannot be
    classified as product-vs-source the way tool_calls can -- every
    [tool_result] line is dropped, and product-tool results are still caught
    via the structured tool_calls loop. [assistant] and [tool_use:...] lines
    are always safe and are kept, including intermediate assistant text that
    never becomes the turn's final agent_message.
    """

    delta = (
        "[assistant] intermediate note: NAME-SENTINEL-abc\n"
        "[tool_use:Read] {\"file_path\": \"primary.csv\"}\n"
        "[tool_result] \"SALARY-SENTINEL-xyz\""
    )
    surfaces = tier_module._leakable_turn_surfaces([_turn(transcript_delta=delta)])
    blob = json.dumps(surfaces)
    assert "NAME-SENTINEL-abc" in blob
    assert "SALARY-SENTINEL-xyz" not in blob


@pytest.mark.parametrize(
    "turns",
    [
        ["not-a-mapping"],
        [_turn(tool_calls="not-a-sequence")],
        [_turn(tool_calls=["not-a-mapping"])],
        [_turn(tool_calls=[{"name": 17, "result": {"content": "NAME-SENTINEL-abc"}}])],
    ],
    ids=["turn", "tool_calls", "call", "unnamed-tool"],
)
def test_a_malformed_transcript_shape_is_scanned_whole_not_skipped(turns: list[object]) -> None:
    """Malformation must not narrow the scan.

    Each shape here is one the exemption logic cannot classify. Dropping an
    unclassifiable surface would let a leak hide behind a shape the scan does
    not recognise, so the unrecognised value is scanned in full instead.
    """

    for turn in turns:
        if isinstance(turn, dict):
            for call in turn.get("tool_calls", []) if isinstance(turn.get("tool_calls"), list) else []:
                if isinstance(call, dict):
                    call.setdefault("result", {"content": "NAME-SENTINEL-abc"})
    blob = json.dumps(tier_module._leakable_turn_surfaces(turns))
    assert "not-a-mapping" in blob or "NAME-SENTINEL-abc" in blob or "not-a-sequence" in blob


def test_operator_observations_report_unmatched_and_ground_truth_turns(tmp_path: Path) -> None:
    """A reader must be able to tell how many turns the operator answered

    from its declared brief versus how many it could not answer at all, not
    just read byte-identical operator replies (the deadlock this guards
    against left no distinguishing trace in earlier observations).
    """

    opening = "Improve visibility."
    sheet = answer_sheet_from_mapping(
        {
            "version": 1,
            "scenario_id": "obs-test",
            "opening_message": opening,
            "turns": [opening, "Please continue.", "Please continue again."],
            "source_answers": {"source": "Use the source."},
            "decision_answers": {},
            "status_answers": {},
            "opening_forbidden_terms": ["source"],
            "open_decision_markers": ["[DECISION NEEDED]"],
            "obstacle_terms": [],
            "ground_truth": {
                "value_col": {"terms": ["value", "column"], "fact": "It is the recognized dollar amount."},
            },
        }
    )
    persona = load_persona(ROOT / "scenarios/_personas/smoke.yaml")
    script = OperatorScript.from_components(
        persona,
        sheet,
        turns=sheet.turns,
        turn_budget=3,
        phase_by_turn={1: 1, 2: 2, 3: 3},
    )
    responses = [
        TurnResult(agent_message="What does the value column represent?"),
        TurnResult(agent_message="What is the endpoint retry policy?"),
        TurnResult(agent_message="Yes, please proceed.", reported=True),
    ]
    result = OperatorEngine(script, InMemoryTransport(responses)).run()

    tier_module._write_operator_observations(tmp_path, result)
    payload = json.loads((tmp_path / "operator-observations.json").read_text())

    assert payload["operator_ground_truth_turn_count"] == 1
    assert payload["operator_unmatched_turn_count"] == 1
    assert payload["operator_repeat_suppressed_count"] == 0
    assert all(turn["operator_repeat_suppressed"] is False for turn in payload["turns"])
    assert payload["turns"][0]["operator_answered_from_ground_truth"] is True
    assert payload["turns"][0]["operator_matched"] is True
    assert payload["turns"][0]["operator_matched_rule_id"] == "ground_truth.value_col"
    assert payload["turns"][1]["operator_matched"] is False
    assert payload["turns"][1]["operator_answered_from_ground_truth"] is False
    assert payload["turns"][1]["operator_matched_rule_id"] == "unmatched.source_question"
    assert payload["turns"][2]["operator_matched"] is True


def test_operator_observations_do_not_count_a_withheld_fact_as_answered(tmp_path: Path) -> None:
    """A suppressed re-serve sent nothing from the brief, so it must not be

    counted as a turn the operator answered from the brief. Counting it would
    make a run that stated one fact and then went quiet read identically to a
    run that answered twice -- exactly the "5 of 7 turns answered from the
    brief" reading the count exists to support.
    """

    opening = "Improve visibility."
    sheet = answer_sheet_from_mapping(
        {
            "version": 1,
            "scenario_id": "obs-repeat",
            "opening_message": opening,
            "turns": [opening, "Please continue.", "Please continue again."],
            "source_answers": {"source": "Use the source."},
            "decision_answers": {},
            "status_answers": {},
            "opening_forbidden_terms": ["source"],
            "open_decision_markers": ["[DECISION NEEDED]"],
            "obstacle_terms": [],
            "ground_truth": {
                "value_col": {"terms": ["value", "column"], "fact": "It is the recognized dollar amount."},
            },
        }
    )
    persona = load_persona(ROOT / "scenarios/_personas/smoke.yaml")
    script = OperatorScript.from_components(
        persona,
        sheet,
        turns=sheet.turns,
        turn_budget=3,
        phase_by_turn={1: 1, 2: 2, 3: 3},
    )
    responses = [
        TurnResult(agent_message="What does the value column represent?"),
        TurnResult(agent_message="What does the value column represent?"),
        TurnResult(agent_message="Understood.", reported=True),
    ]
    transport = InMemoryTransport(responses)
    result = OperatorEngine(script, transport).run()

    tier_module._write_operator_observations(tmp_path, result)
    payload = json.loads((tmp_path / "operator-observations.json").read_text())

    assert transport.message_texts[1] == "It is the recognized dollar amount."
    assert transport.message_texts[2] == "Please continue again."
    assert payload["operator_repeat_suppressed_count"] == 1
    assert payload["operator_ground_truth_turn_count"] == 1
    assert payload["turns"][0]["operator_repeat_suppressed"] is False
    assert payload["turns"][0]["operator_answered_from_ground_truth"] is True
    assert payload["turns"][1]["operator_repeat_suppressed"] is True
    assert payload["turns"][1]["operator_matched_rule_id"] == "ground_truth.value_col"
    assert payload["turns"][1]["operator_answered_from_ground_truth"] is False


def test_a_repeated_answer_is_suppressed_end_to_end_through_the_replay_path(tmp_path: Path) -> None:
    """The whole path, not the writer in isolation.

    ``TierRunner.run()`` owns the artifact root the observations are written
    under, so the flag is asserted where a grader would read it, alongside the
    operator text a transcript reader would see.
    """

    scenario = make_scenario("repeat-replay", turns=3)
    recording = recording_for(scenario, responses_for(scenario))

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording},
        evidence_root=tmp_path / "evidence",
    ).run()

    run = result.scenario_runs[0]
    payload = json.loads(
        (Path(run.evidence_bundle_dir) / "artifacts" / "operator-observations.json").read_text(encoding="utf-8")
    )

    assert payload["operator_repeat_suppressed_count"] == 2
    assert [turn["operator_repeat_suppressed"] for turn in payload["turns"]] == [False, True, True]
    sent = [turn.operator_message.text for turn in run.replay_recording.turns]
    assert sent == ["Improve visibility.", "Use the source.", "Please continue 2."]


def test_a_repeated_answer_is_suppressed_end_to_end_on_the_live_path(tmp_path: Path) -> None:
    """The same property on the ``session_factory=`` branch.

    A fix verified only under ``replay_recordings=`` has already been bypassed
    entirely on the live branch in this package, so both are driven.
    """

    scenario = make_scenario("repeat-live", turns=3)
    responses = responses_for(scenario)
    (tmp_path / "env").mkdir()

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        session_factory=lambda *_args: InMemoryTransport(responses),
        environment_root=tmp_path / "env",
        evidence_root=tmp_path / "evidence",
    ).run()

    run = result.scenario_runs[0]
    payload = json.loads(
        (Path(run.evidence_bundle_dir) / "artifacts" / "operator-observations.json").read_text(encoding="utf-8")
    )

    assert payload["operator_repeat_suppressed_count"] == 2
    assert [turn["operator_repeat_suppressed"] for turn in payload["turns"]] == [False, True, True]
    sent = [turn.operator_message.text for turn in run.replay_recording.turns]
    assert sent == ["Improve visibility.", "Use the source.", "Please continue 2."]


def test_a_shipped_brief_actually_fires_in_a_scenario_level_run(tmp_path: Path) -> None:
    """The ground-truth brief is exercised through a real shipped scenario.

    Unit tests build their own answer sheets, and the existing replays never
    ask anything the scripted answer bank fails to cover -- so before this,
    every committed brief could be deleted with the suite still green and the
    capability was inert in the packages it shipped in. This drives the real
    zero-row scenario through TierRunner with an agent turn asking exactly the
    kind of column-semantics question the first live run deadlocked on, and
    asserts the operator answered it from the brief.

    It deliberately does not assert a clean verdict: the point is that the
    brief fired and was recorded, not that this altered transcript still
    satisfies every gate.
    """

    scenario, recordings = populated_zero_row_recordings(
        tmp_path, opening_agent_message="What does the value column actually represent?"
    )

    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recordings},
    ).run()

    run = result.scenario_runs[0]
    rows = [json.loads(line) for line in run.ledger_bytes.splitlines()]
    rule_ids = [row.get("matched_rule_id") for row in rows]
    assert "ground_truth.value_column" in rule_ids, (
        f"no ground-truth answer reached the ledger; rule ids were {rule_ids!r}"
    )
    assert any(
        isinstance(row.get("claim"), Mapping)
        and row["claim"].get("operator_answered_from_ground_truth") is True
        for row in rows
    )
