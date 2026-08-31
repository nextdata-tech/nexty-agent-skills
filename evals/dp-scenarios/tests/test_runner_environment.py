"""Guard tests for fresh run homes, complete manifests, and secret isolation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

import pytest

from dp_scenarios.operator import OperatorScript
from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.runner import environment as environment_module
from dp_scenarios.runner.environment import PinnedVersions, RunEnvironment, RunEnvironmentError
from dp_scenarios.canary import probe
from dp_scenarios.synthgen.generator import GenerationResult


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
    with pytest.raises(RunEnvironmentError, match="runtime_wheel_version"):
        PinnedVersions.from_mapping(
            {
                "skill_pack_version": "skills-1",
                "supervisor_version": "supervisor-1",
                "mock_api_version": "mock-1",
                "canary_claims_hash": "claims-1",
            }
        )


def test_empty_pinned_value_is_a_hard_error() -> None:
    with pytest.raises(RunEnvironmentError, match="skill_pack_version"):
        PinnedVersions.from_mapping(
            {
                "skill_pack_version": "",
                "supervisor_version": "supervisor-1",
                "runtime_wheel_version": "wheel-1",
                "mock_api_version": "mock-1",
                "canary_claims_hash": "claims-1",
            }
        )


@pytest.mark.parametrize(
    "field",
    [
        "skill_pack_version",
        "supervisor_version",
        "runtime_wheel_version",
        "mock_api_version",
        "canary_claims_hash",
        "agent_model_id",
    ],
)
def test_pinned_versions_reject_whitespace_only_values(field: str) -> None:
    values: dict[str, object] = {
        "skill_pack_version": "skills-1",
        "supervisor_version": "supervisor-1",
        "runtime_wheel_version": "wheel-1",
        "mock_api_version": "mock-1",
        "canary_claims_hash": "claims-1",
        "agent_model_id": "replay",
    }
    values[field] = " \t"

    with pytest.raises(RunEnvironmentError, match=field):
        PinnedVersions(**values)  # type: ignore[arg-type]


def test_from_mapping_rejects_each_missing_required_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Keep this test on the mapping guard itself; otherwise __post_init__'s
    # duplicate scalar check would mask a disabled missing-values branch.
    monkeypatch.setattr(environment_module, "_required_text", lambda value, field_name: value)
    complete: dict[str, object] = {
        "skill_pack_version": "skills-1",
        "supervisor_version": "supervisor-1",
        "runtime_wheel_version": "wheel-1",
        "mock_api_version": "mock-1",
        "canary_claims_hash": "claims-1",
    }

    for field in complete:
        missing = {key: value for key, value in complete.items() if key != field}
        with pytest.raises(RunEnvironmentError, match=field):
            PinnedVersions.from_mapping(missing)


@pytest.mark.parametrize("value", [None, 7])
def test_from_mapping_rejects_non_text_agent_model_id(value: object) -> None:
    with pytest.raises(RunEnvironmentError, match="agent_model_id"):
        PinnedVersions.from_mapping(
            {
                "skill_pack_version": "skills-1",
                "supervisor_version": "supervisor-1",
                "runtime_wheel_version": "wheel-1",
                "mock_api_version": "mock-1",
                "canary_claims_hash": "claims-1",
                "agent_model_id": value,
            }
        )


def test_fixture_manifest_without_base_instant_is_a_hard_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = make_scenario()

    def missing_base(_scenario: FixtureScenario, out_dir: str | Path) -> GenerationResult:
        target = Path(out_dir)
        return GenerationResult(
            "zero_row_optional",
            29,
            target,
            target / "data",
            target / "gold",
            target / "fixture-manifest.json",
            {"fixture_hash": "fixture"},
        )

    monkeypatch.setattr(FixtureScenario, "generate_fixture", missing_base)
    with pytest.raises(RunEnvironmentError, match="base_instant"):
        with RunEnvironment(scenario, pins(), root=tmp_path):
            pass


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


def test_fixture_hash_is_derived_from_the_generated_fixture(tmp_path: Path) -> None:
    first_scenario = make_scenario()
    second_scenario = FixtureScenario(
        first_scenario.package_dir,
        first_scenario.id,
        first_scenario.tier,
        first_scenario.seed + 1,
        first_scenario.turn_budget,
        first_scenario.script,
    )
    (tmp_path / "first").mkdir()
    (tmp_path / "second").mkdir()
    with RunEnvironment(first_scenario, pins(), root=tmp_path / "first") as first:
        first_hash = first.manifest.fixture_dir_hash
    with RunEnvironment(second_scenario, pins(), root=tmp_path / "second") as second:
        second_hash = second.manifest.fixture_dir_hash

    assert first_hash != second_hash


def test_ledger_open_failure_removes_the_disposable_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = make_scenario()
    ledger_path: dict[str, Path] = {}

    def fail_open(path: Path, manifest: object) -> object:
        ledger_path["path"] = path
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(environment_module.LedgerStore, "open", fail_open)
    environment = RunEnvironment(scenario, pins(), root=tmp_path)

    with pytest.raises(RuntimeError, match="ledger unavailable"):
        environment.prepare()

    assert environment._temporary is None
    assert not ledger_path["path"].parent.exists()


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


def test_canary_environment_allowlist_excludes_parent_home_and_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("HOME", "/parent/home")
    monkeypatch.setenv("USERPROFILE", r"C:\parent\profile")
    monkeypatch.setenv("PARENT_SECRET", "must-not-cross")

    def fake_subprocess_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess(args[0], 0, "", "")  # type: ignore[arg-type]

    monkeypatch.setattr(probe.subprocess, "run", fake_subprocess_run)
    probe._run(["supervisor", "check"], closure=tmp_path)

    environment = captured["env"]
    assert isinstance(environment, dict)
    assert "HOME" not in environment
    assert "USERPROFILE" not in environment
    assert "PARENT_SECRET" not in environment


def test_replay_manifest_mismatch_is_rejected(tmp_path: Path) -> None:
    scenario = make_scenario()
    with RunEnvironment(scenario, pins(), root=tmp_path) as environment:
        manifest = environment.manifest.to_dict()
    manifest["skill_pack_version"] = "different"

    with pytest.raises(RunEnvironmentError, match="replay manifest mismatch"):
        with RunEnvironment(scenario, pins(), root=tmp_path, manifest_override=manifest):
            pass
