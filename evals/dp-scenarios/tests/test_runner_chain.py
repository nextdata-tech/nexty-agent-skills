"""B11 chain transition uses runner history and keeps older scripts unchanged."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from dp_scenarios.canary import Verdict
from dp_scenarios.grading.score import TerminalState as ScoreTerminalState
from dp_scenarios.grading.statistics import RepeatabilityTier
from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript, TerminalState
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult
from dp_scenarios.runner.chain import CHAIN_SCHEMA, ChainController, _stage_constraint, _typed_stage_constraint
from dp_scenarios.runner.session import RecordingSession
from dp_scenarios.runner import CanaryResult, PinnedVersions
from dp_scenarios.runner.tier import TierError, TierRunner, _replay_verification
from dp_scenarios.runner.supervisor_history import (
    CAPTURES_SCHEMA,
    DEFINITION_EXPORT_SCHEMA,
    PUBLICATION_SCHEMA,
    RUN_RECORDS_SCHEMA,
)
from dp_scenarios.scenario import ChainSpec, RepeatabilitySpec, ScenarioError, _parse_chain, load_scenario
import dp_scenarios.scenario as scenario_module


ROOT = Path(__file__).parents[1]
STAGES = ("prospecting", "qualification", "negotiation", "closed_won", "closed_lost")
SPEC = ChainSpec(2, "crm_deals", "v1", "v2", "crm_deals_v2", STAGES)
VERIFIER = b'''from nxd import data_product
from nxd.core.context import VerifyResult, VerifyResultEnum
@data_product.on_verify()
def check(output):
    if row.stage not in ("prospecting", "qualification", "negotiation", "closed_won", "closed_lost"):
        return VerifyResult(VerifyResultEnum.FAILED, {})
    return VerifyResult(VerifyResultEnum.PASS, {})
'''
CAPTURED_SQL_VERIFIER = (ROOT / "tests/fixtures/pipeline_declared_stage.py").read_bytes()


def _sha(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _write(root: Path, name: str, payload: object) -> None:
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def _history(root: Path, *, verifier: bytes = VERIFIER, capture: bool = True) -> dict[str, object]:
    release = {
        "workflow_id": "prefix-workflow", "run_id": "prefix-run", "publish_sequence": "1",
        "artifact_id": "artifact-1", "definition_id": "definition-1", "attributed_by": "built_run",
        "changed_after_first_seen": False,
    }
    _write(root, "publication-history.json", {"schema": PUBLICATION_SCHEMA, "releases": [release]})
    _write(root, "run-records.json", {"schema": RUN_RECORDS_SCHEMA, "runs": [{
        "workflow_id": "prefix-workflow", "run_id": "prefix-run", "status": "Published",
        "definition_id": "definition-1", "capture_sha256": "sha256:" + "a" * 64,
        "artifact_id": "artifact-1", "publish_sequence": "1",
    }]})
    if capture:
        folder = root / "supervisor-captures" / ("a" * 64) / "contracts"
        folder.mkdir(parents=True)
        (folder / "stage.py").write_bytes(verifier)
        _write(root, "supervisor-captures.json", {"schema": CAPTURES_SCHEMA, "captures": [{
            "capture_sha256": "sha256:" + "a" * 64, "run_ids": ["prefix-run"],
            "files": [{"path": "contracts/stage.py", "sha256": _sha(verifier)}],
        }]})
        _write(root, "definition-export.json", {"schema": DEFINITION_EXPORT_SCHEMA, "definitions": [{
            "definition_id": "definition-1", "inventory_valid": True,
            "output_promises": [{
                "source": "contracts/stage.py", "source_in_inventory": True,
                "source_hash_verified": True, "source_sha256": _sha(verifier),
            }],
        }]})
    return release


class Source:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.state = "v1"

    def snapshot_runtime_state(self) -> dict[str, object]:
        return {"current_states": {"crm_deals": self.state}}

    def set_dataset_state(self, family: str, state: str) -> None:
        assert family == "crm_deals"
        self.calls.append("source")
        self.state = state


def _controller(root: Path, calls: list[str]) -> ChainController:
    return ChainController(
        SPEC, root, Source(calls),
        lambda overlay: calls.append("overlay:" + overlay),
        lambda prefix: calls.append("suffix:" + str(prefix)),
    )


def test_first_observed_publication_switches_once_after_source_and_freezes_release(tmp_path: Path) -> None:
    calls: list[str] = []
    controller = _controller(tmp_path, calls)
    controller.observe(1)
    assert controller.state["status"] == "waiting"
    release = _history(tmp_path)
    controller.observe(2)
    controller.observe(3)

    assert calls == ["source", "overlay:crm_deals_v2", "suffix:2"]
    assert controller.state["prefix_release"] == release
    assert controller.state["turn"] == 2
    assert json.loads((tmp_path / "chain-state.json").read_text())["schema"] == CHAIN_SCHEMA


def test_no_publication_and_invalid_prefix_are_failures(tmp_path: Path) -> None:
    controller = _controller(tmp_path, [])
    assert controller.finalize() == {
        "schema": CHAIN_SCHEMA, "status": "failed", "reason": "drift_prefix_publication_missing",
    }
    invalid_root = tmp_path / "invalid"
    invalid_root.mkdir()
    _history(invalid_root, verifier=b"# five stages in prose only\n")
    calls: list[str] = []
    invalid = _controller(invalid_root, calls)
    invalid.observe(1)
    assert invalid.state["status"] == "failed"
    assert invalid.state["reason"] == "drift_prefix_invalid"
    assert calls == []


def test_published_prefix_with_missing_retained_capture_is_ungraded(tmp_path: Path) -> None:
    _history(tmp_path, capture=False)
    controller = _controller(tmp_path, [])
    controller.observe(1)
    assert controller.state["status"] == "ungraded"
    assert controller.state["reason"] == "drift_capture_unavailable"


def test_published_prefix_without_executable_enforcement_is_failed(tmp_path: Path) -> None:
    _history(tmp_path)
    export = json.loads((tmp_path / "definition-export.json").read_text())
    export["definitions"][0]["output_promises"] = []
    export["definitions"][0]["model_promises"] = []
    _write(tmp_path, "definition-export.json", export)
    controller = _controller(tmp_path, [])
    controller.observe(1)
    assert controller.state["status"] == "failed"
    assert controller.state["reason"] == "drift_prefix_invalid"


def test_promised_typed_enum_in_retained_models_file_can_authorize_switch(tmp_path: Path) -> None:
    _history(tmp_path, verifier=b"# no custom verifier here\n")
    typed = b"from typing import Literal\nclass Deal:\n    stage: Literal['prospecting', 'qualification', 'negotiation', 'closed_won', 'closed_lost']\n"
    (tmp_path / "supervisor-captures" / ("a" * 64) / "models.py").write_bytes(typed)
    captures = json.loads((tmp_path / "supervisor-captures.json").read_text())
    captures["captures"][0]["files"].append({"path": "models.py", "sha256": _sha(typed)})
    _write(tmp_path, "supervisor-captures.json", captures)
    export = json.loads((tmp_path / "definition-export.json").read_text())
    export["definitions"][0]["output_promises"] = []
    export["definitions"][0]["model_promises"] = [{"models": ["Deal"]}]
    _write(tmp_path, "definition-export.json", export)
    controller = _controller(tmp_path, [])
    controller.observe(1)
    assert controller.state["status"] == "switched"


def test_source_switch_failure_withholds_overlay_and_suffix(tmp_path: Path) -> None:
    _history(tmp_path)
    calls: list[str] = []
    source = Source(calls)
    source.state = "v2"
    controller = ChainController(
        SPEC, tmp_path, source,
        lambda _overlay: calls.append("overlay"),
        lambda _prefix: calls.append("suffix"),
    )
    controller.observe(1)
    assert controller.state["status"] == "ungraded"
    assert controller.state["reason"] == "drift_source_switch_unavailable"
    assert calls == []


def test_ast_precondition_requires_executable_constraint_and_promised_literal() -> None:
    assert _stage_constraint(VERIFIER, STAGES)
    assert not _stage_constraint(b"# stage not in prospecting qualification negotiation closed_won closed_lost\n", STAGES)
    assert _stage_constraint(CAPTURED_SQL_VERIFIER, STAGES)
    typed = b"from typing import Literal\nclass Deal:\n    stage: Literal['prospecting', 'qualification', 'negotiation', 'closed_won', 'closed_lost']\n"
    assert _typed_stage_constraint(typed, STAGES, {"Deal"})
    assert not _typed_stage_constraint(typed, STAGES, {"Unpromised"})


def test_python_stage_precondition_resolves_fixed_local_stage_literal() -> None:
    local_literal = b'''from nxd import data_product
from nxd.core.context import VerifyResult, VerifyResultEnum
@data_product.on_verify()
def check(output):
    official = ("prospecting", "qualification", "negotiation", "closed_won", "closed_lost")
    if row.stage not in official:
        return VerifyResult(VerifyResultEnum.FAILED, {})
    return VerifyResult(VerifyResultEnum.PASS, {})
'''
    rebound = local_literal.replace(
        b'    if row.stage not in official:',
        b'    official = ("prospecting",)\n    if row.stage not in official:',
    )
    mutated = local_literal.replace(
        b'official = ("prospecting", "qualification", "negotiation", "closed_won", "closed_lost")',
        b'official = ["prospecting", "qualification", "negotiation", "closed_won", "closed_lost"]\n    official.append("paused")',
    )

    assert _stage_constraint(local_literal, STAGES)
    assert not _stage_constraint(rebound, STAGES)
    assert not _stage_constraint(mutated, STAGES)
    assert not _stage_constraint(
        local_literal.replace(
            b"if row.stage not in official:",
            b"if row.stage not in official == ():",
        ),
        STAGES,
    )


@pytest.mark.parametrize(
    "source",
    [
        CAPTURED_SQL_VERIFIER.replace(
            b"DECLARED_STAGES = (\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\", \"closed_lost\")",
            b"DECLARED_STAGES = (\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\")",
        ),
        CAPTURED_SQL_VERIFIER.replace(
            b"DECLARED_STAGES = (\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\", \"closed_lost\")",
            b"DECLARED_STAGES = (\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\", \"closed_lost\", \"paused\")",
        ),
        CAPTURED_SQL_VERIFIER.replace(
            b"DECLARED_STAGES = (\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\", \"closed_lost\")",
            b"DECLARED_STAGES = (\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\", \"closed_won\")",
        ),
        CAPTURED_SQL_VERIFIER.replace(
            b"list(DECLARED_STAGES)", b"list(UNUSED_STAGES)"
        ).replace(
            b"DECLARED_STAGES = (\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\", \"closed_lost\")",
            b"DECLARED_STAGES = (\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\", \"closed_lost\")\nUNUSED_STAGES = (\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\", \"closed_lost\")",
        ),
        CAPTURED_SQL_VERIFIER.replace(
            b"for _ in DECLARED_STAGES", b"for _ in range(5)"
        ).replace(b"list(DECLARED_STAGES)", b"[]"),
        CAPTURED_SQL_VERIFIER.replace(
            b'f"SELECT stage, COUNT(*) FROM {table} "\n            f"WHERE stage IS NULL OR stage NOT IN ({placeholders}) GROUP BY stage"',
            b'f"SELECT stage FROM {table} WHERE stage NOT IN (__BOUND__)"',
        ),
        CAPTURED_SQL_VERIFIER.replace(
            b"WHERE stage IS NULL OR stage NOT IN", b"WHERE status IS NULL OR status NOT IN"
        ),
        CAPTURED_SQL_VERIFIER.replace(
            b"if total == 0 or offending:", b"if total == 0 or not offending:"
        ),
        CAPTURED_SQL_VERIFIER.replace(
            b"    if total == 0 or offending:",
            b"    offending.clear()\n    if total == 0 or offending:",
        ),
        CAPTURED_SQL_VERIFIER.replace(
            b"        return VerifyResult(\n            VerifyResultEnum.FAILED,",
            b"        return VerifyResult(\n            VerifyResultEnum.PASS,",
        ),
        CAPTURED_SQL_VERIFIER.replace(
            b"            VerifyResultEnum.FAILED,",
            b"            VerifyResultEnum.FAILED if False else VerifyResultEnum.PASS,",
        ),
        CAPTURED_SQL_VERIFIER.replace(
            b"DECLARED_STAGES = (\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\", \"closed_lost\")",
            b"DECLARED_STAGES = (\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\", \"closed_lost\")\nDECLARED_STAGES = (\"prospecting\",)",
        ),
    ],
)
def test_sql_stage_precondition_rejects_unlinked_or_non_failing_checks(source: bytes) -> None:
    assert not _stage_constraint(source, STAGES)


def test_sql_stage_precondition_accepts_fixed_literal_list_and_frozenset() -> None:
    list_form = CAPTURED_SQL_VERIFIER.replace(
        b"DECLARED_STAGES = (\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\", \"closed_lost\")",
        b"DECLARED_STAGES = [\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\", \"closed_lost\"]",
    )
    frozen_form = CAPTURED_SQL_VERIFIER.replace(
        b"DECLARED_STAGES = (\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\", \"closed_lost\")",
        b"DECLARED_STAGES = frozenset((\"prospecting\", \"qualification\", \"negotiation\", \"closed_won\", \"closed_lost\"))",
    )
    mutated_list = list_form.replace(
        b"\n\n\n@data_product.on_verify()",
        b"\nDECLARED_STAGES.append(\"paused\")\n\n\n@data_product.on_verify()",
    )
    aliased_list = list_form.replace(
        b"\n\n\n@data_product.on_verify()",
        b"\n_STAGE_ALIAS = DECLARED_STAGES\n_STAGE_ALIAS[0] = \"paused\"\n\n\n@data_product.on_verify()",
    )

    assert _stage_constraint(list_form, STAGES)
    assert _stage_constraint(frozen_form, STAGES)
    assert not _stage_constraint(mutated_list, STAGES)
    assert not _stage_constraint(aliased_list, STAGES)


def test_sql_stage_precondition_accepts_explicit_nonempty_offending_rows_check() -> None:
    source = CAPTURED_SQL_VERIFIER.replace(
        b"if total == 0 or offending:", b"if total == 0 or len(offending) > 0:"
    )
    assert _stage_constraint(source, STAGES)


def test_sql_stage_precondition_preserves_literal_sql_rejection() -> None:
    literal_sql = b'''from nxd import data_product
from nxd.core.context import VerifyResult, VerifyResultEnum
@data_product.on_verify()
def verify(output):
    connection = output.connection()
    offending = connection.execute(
        "SELECT stage FROM pipeline WHERE stage NOT IN ('prospecting', 'qualification', 'negotiation', 'closed_won', 'closed_lost')"
    ).fetchall()
    if offending:
        return VerifyResult(VerifyResultEnum.FAILED, {})
    return VerifyResult(VerifyResultEnum.PASS, {})
'''
    assert _stage_constraint(literal_sql, STAGES)


def test_chain_schema_is_strict_and_existing_hash_is_unchanged() -> None:
    scenario = load_scenario(ROOT / "scenarios/crm-pipeline")
    assert scenario.chain is None
    assert scenario.script_hash == scenario.operator_script_hash
    assert replace(scenario, chain=SPEC).script_hash != scenario.script_hash
    answer = SimpleNamespace(decision_overlay_ids={"crm_deals_v2"})
    route = SimpleNamespace(routes=[SimpleNamespace(
        state_family="crm_deals", initial_state="v1", states={"v1": object(), "v2": object()}
    )])
    declaration = SPEC.to_mapping()
    parsed = _parse_chain(declaration, answer_sheet=answer, route_table=route, turn_count=4)
    assert parsed == SPEC
    with pytest.raises(ScenarioError, match="unknown|requires"):
        _parse_chain({**declaration, "future_decision": "leak"}, answer_sheet=answer, route_table=route, turn_count=4)
    with pytest.raises(ScenarioError, match="leave at least one suffix"):
        _parse_chain({**declaration, "prefix_turns": 4}, answer_sheet=answer, route_table=route, turn_count=4)
    with pytest.raises(ScenarioError, match="chain must be a mapping"):
        _parse_chain(None, answer_sheet=answer, route_table=route, turn_count=4)


def test_follow_up_context_receives_runner_artifact_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    scenario = load_scenario(ROOT / "scenarios/crm-pipeline")
    seen: list[Path | None] = []
    kind = SimpleNamespace(handler=lambda _scenario, _target, _settings, context: (
        seen.append(context.artifact_root) or {"status": "examined", "passed": False, "findings": []}
    ))
    monkeypatch.setattr(scenario_module.followups, "get", lambda _name: kind)
    scenario.follow_up_check({}, artifact_root=tmp_path)
    assert seen == [tmp_path]


def test_chained_native_resume_refuses_before_environment_start(tmp_path: Path) -> None:
    runner = object.__new__(TierRunner)
    runner.native_resume_checkpoint = tmp_path / "checkpoint.json"
    with pytest.raises(TierError, match="native resume of a chained scenario"):
        runner._run_scenario_epochs(SimpleNamespace(chain=SPEC), pins=None)  # type: ignore[arg-type]


def test_unpublished_prefix_scores_failed_in_tier(tmp_path: Path) -> None:
    base = load_scenario(ROOT / "scenarios/crm-pipeline")
    scenario = replace(
        base,
        chain=SPEC,
        repeatability=RepeatabilitySpec(
            RepeatabilityTier.DEMONSTRATED_ONCE, 1, "demonstrated_once", ("build",), None, None
        ),
    )
    transport = InMemoryTransport([
        TurnResult(agent_message="Which source should I use?"),
        TurnResult(agent_message="I am working on it."),
    ])
    environments = tmp_path / "runs"
    environments.mkdir()
    result = TierRunner(
        [scenario],
        pins=PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1"),
        canary=CanaryResult(Verdict("clean", (), ()), claims_hash="claims-1"),
        session_factory=lambda *_args: transport,
        environment_root=environments,
    ).run()
    run = result.scenarios[0].runs[0]
    assert run.stop_condition == "chain_prefix_failed"
    assert run.score.state is ScoreTerminalState.FAILED
    assert len(transport.message_texts) == 2


def test_tier_reports_chained_follow_up_reason_once(tmp_path: Path) -> None:
    base = load_scenario(ROOT / "scenarios/crm-pipeline-drift")
    assert base.chain is not None
    scenario = replace(
        base,
        chain=replace(base.chain, prefix_turns=2),
        repeatability=RepeatabilitySpec(
            RepeatabilityTier.DEMONSTRATED_ONCE, 1, "demonstrated_once", ("build",), None, None
        ),
    )
    result = TierRunner(
        [scenario],
        pins=PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1"),
        canary=CanaryResult(Verdict("clean", (), ()), claims_hash="claims-1"),
        session_factory=lambda *_args: InMemoryTransport([
            TurnResult(agent_message="Working on the pipeline."),
            TurnResult(agent_message="No publication yet."),
        ]),
        environment_root=tmp_path,
    ).run()
    follow_up = result.scenarios[0].runs[0].score.gates["follow-up"]
    assert follow_up.codes.count("drift_prefix_publication_missing") == 1


def _script() -> OperatorScript:
    sheet = answer_sheet_from_mapping({
        "version": 1, "scenario_id": "chain-test", "opening_message": "Build a pipeline.",
        "turns": [
            {"text": "Build a pipeline.", "substitute_reply": False},
            {"text": "Unused prefix.", "substitute_reply": False},
            {"text": "It is a new week. Refresh the numbers.", "substitute_reply": False},
            {"text": "Continue the refresh.", "substitute_reply": False},
        ],
        "source_answers": {"source": "Use the CRM source."},
        "decision_answers": {"choice": {
            "terms": ["option"], "answer": "Choose it.",
            "available_after_overlay": "crm_deals_v2",
        }},
        "status_answers": {"status": "In progress."},
        "opening_forbidden_terms": ["hidden-marker"], "open_decision_markers": ["[DECISION NEEDED]"],
        "obstacle_terms": [],
    })
    return OperatorScript.from_components(
        load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet,
        turn_budget=4, phase_by_turn={1: 1, 2: 2, 3: 5, 4: 7},
    )


def test_engine_never_sends_suffix_without_switch_and_discards_unused_prefix() -> None:
    script = _script()
    no_switch = InMemoryTransport([TurnResult(agent_message="What source?"), TurnResult(agent_message="Done")])
    result = OperatorEngine(script, no_switch, chain_prefix_turns=2).run()
    assert result.terminal_state is TerminalState.CHAIN_PREFIX_FAILED
    assert no_switch.message_texts == ("Build a pipeline.", "Unused prefix.")

    live = InMemoryTransport([TurnResult(agent_message="What source?"), TurnResult(agent_message="Working"), TurnResult(agent_message="Done")])
    engine: OperatorEngine | None = None

    def boundary(_snapshot: object, turn: int) -> None:
        if turn == 1:
            assert engine is not None
            engine.activate_decision_overlay("crm_deals_v2")
            engine.skip_to_suffix(2)

    recording = RecordingSession(live, on_turn_complete=boundary)
    engine = OperatorEngine(script, recording, chain_prefix_turns=2)
    switched = engine.run()
    assert switched.terminal_state is not TerminalState.CHAIN_PREFIX_FAILED
    assert live.message_texts == ("Build a pipeline.", "It is a new week. Refresh the numbers.", "Continue the refresh.")
    replay = recording.recording(metadata={
        "chain_state": {
            "schema": CHAIN_SCHEMA, "status": "switched", "turn": 1,
            "prefix_release": {"workflow_id": "prefix-workflow"},
        },
        "publication_schedule_by_turn": [
            {"turn": turn, "snapshot": None} for turn in range(1, 4)
        ],
    })
    assert _replay_verification(
        SimpleNamespace(script=script, chain=SPEC), replay, switched,
        generated_operator=False,
    )[0] == "verified"
