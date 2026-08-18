"""Guard tests for fresh run homes, complete manifests, and secret isolation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from dp_scenarios.operator import OperatorScript
from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.runner.environment import EnvironmentError, PinnedVersions, RunEnvironment


ROOT = Path(__file__).parents[1]


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

    def generate_fixture(self, out_dir: str | Path):
        from dp_scenarios.synthgen import generate_dataset

        return generate_dataset(self.dataset, self.seed, out_dir)


def make_scenario() -> FixtureScenario:
    sheet = answer_sheet_from_mapping(
        {
            "version": 1,
            "scenario_id": "environment-test",
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
    persona = load_persona(ROOT / "scenarios/_personas/smoke.yaml")
    script = OperatorScript.from_components(
        persona,
        sheet,
        turns=sheet.turns,
        turn_budget=1,
        phase_by_turn={1: 1},
    )
    return FixtureScenario(ROOT, "environment-test", "smoke", 29, 1, script)


def pins() -> PinnedVersions:
    return PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1")


def test_missing_pinned_value_is_a_hard_error() -> None:
    with pytest.raises(EnvironmentError, match="runtime_wheel_version"):
        PinnedVersions.from_mapping(
            {
                "skill_pack_version": "skills-1",
                "supervisor_version": "supervisor-1",
                "mock_api_version": "mock-1",
                "canary_claims_hash": "claims-1",
            }
        )


def test_each_environment_gets_a_fresh_home_and_a_row_zero_manifest(tmp_path: Path) -> None:
    scenario = make_scenario()
    with RunEnvironment(scenario, pins(), root=tmp_path, trial_index=0) as first:
        first_home = first.home
        first_manifest = first.manifest.to_dict()
        assert first.ledger_path.read_text(encoding="utf-8").splitlines()[0]
        assert first_manifest["skill_pack_version"] == "skills-1"
        assert first.fixture_dir.joinpath("fixture-manifest.json").is_file()
    with RunEnvironment(scenario, pins(), root=tmp_path, trial_index=1) as second:
        assert second.home != first_home
        assert second.home.is_dir()
        assert second.manifest.trial_index == 1


def test_mock_control_secret_never_enters_agent_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = make_scenario()
    monkeypatch.setenv("EVAL_SOURCE_TOKEN", "harness-only")
    with RunEnvironment(scenario, pins(), root=tmp_path, control_secret="harness-only") as environment:
        values = environment.agent_environment
        assert all("harness-only" not in value for value in values.values())


def test_agent_environment_is_allowlisted_not_parent_environment_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = make_scenario()
    monkeypatch.setenv("PROVIDER_API_KEY", "provider-secret")
    monkeypatch.setenv("UNRELATED_CONTROL_VALUE", "provider-secret-suffix")
    with RunEnvironment(scenario, pins(), root=tmp_path) as environment:
        values = environment.agent_environment

    assert "PROVIDER_API_KEY" not in values
    assert "UNRELATED_CONTROL_VALUE" not in values
    assert values["HOME"].endswith("/home")


def test_replay_manifest_mismatch_is_rejected(tmp_path: Path) -> None:
    scenario = make_scenario()
    with RunEnvironment(scenario, pins(), root=tmp_path) as environment:
        manifest = environment.manifest.to_dict()
    manifest["skill_pack_version"] = "different"

    with pytest.raises(EnvironmentError, match="replay manifest mismatch"):
        with RunEnvironment(scenario, pins(), root=tmp_path, manifest_override=manifest):
            pass
