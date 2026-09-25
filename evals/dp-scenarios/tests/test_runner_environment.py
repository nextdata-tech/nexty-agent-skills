"""Guard tests for fresh run homes, complete manifests, and secret isolation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import socket
import stat
import subprocess
import sys
from urllib.request import Request, urlopen

import pytest

from dp_scenarios.operator import OperatorScript
from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.runner import environment as environment_module
from dp_scenarios.runner.environment import PinnedVersions, RunEnvironment, RunEnvironmentError
from dp_scenarios.mockrest.config import load_config
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


def mock_route_config(*, data_port: int = 0, control_port: int = 0, row_id: str = "row-1"):
    return load_config(
        {
            "version": 1,
            "data_port": data_port,
            "control_port": control_port,
            "auth": {"token": "source-secret", "initial_requests": 2},
            "routes": [
                {
                    "path": "/rows",
                    "method": "GET",
                    "auth_required": True,
                    "response": {"json": [{"id": row_id}]},
                }
            ],
        }
    )


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


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


def test_agent_fixture_excludes_gold_and_sensitive_generation_metadata(tmp_path: Path) -> None:
    with RunEnvironment(make_scenario(), pins(), root=tmp_path) as environment:
        agent_manifest = json.loads((environment.fixture_dir / "fixture-manifest.json").read_text(encoding="utf-8"))
        assert not (environment.fixture_dir / "gold").exists()
        assert (environment.oracle_dir / "gold").is_dir()
        assert "pii_markers" not in agent_manifest
        assert "pii_dictionary" not in agent_manifest
        assert agent_manifest["fixture_scope"] == "agent-visible-data-only"
        assert "file_hashes" not in agent_manifest
        assert str(environment.oracle_dir) not in environment.agent_environment.values()


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


def test_context_manager_preserves_an_in_flight_error_when_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = make_scenario()

    def fail_close(_environment: RunEnvironment) -> None:
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(environment_module.RunEnvironment, "close", fail_close)
    with pytest.raises(ValueError, match="run failed") as error:
        with RunEnvironment(scenario, pins(), root=tmp_path):
            raise ValueError("run failed")

    assert any("RunEnvironment cleanup failed" in note for note in error.value.__notes__)


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


def test_close_releases_remaining_resources_after_one_cleanup_fails() -> None:
    class Resource:
        def __init__(self, method: str, calls: list[str], failure: bool = False) -> None:
            self.method = method
            self.calls = calls
            self.failure = failure

        def __getattr__(self, name: str):
            if name != self.method:
                raise AttributeError(name)

            def close() -> None:
                self.calls.append(name)
                if self.failure:
                    raise RuntimeError(f"{name} failed")

            return close

    calls: list[str] = []
    environment = RunEnvironment(make_scenario(), pins())
    environment._live_transport = Resource("cleanup", calls, failure=True)
    environment._ledger = Resource("close", calls)
    environment._mock_source = Resource("stop", calls)
    environment._temporary = Resource("cleanup", calls)

    with pytest.raises(RuntimeError, match="cleanup failed"):
        environment.close()

    assert calls == ["cleanup", "close", "stop", "cleanup"]
    assert environment._live_transport is None
    assert environment._ledger is None
    assert environment._mock_source is None
    assert environment._temporary is None


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


def test_native_continuation_requires_an_explicit_persistent_run_root(tmp_path: Path) -> None:
    with pytest.raises(RunEnvironmentError, match="persistent run root"):
        with RunEnvironment(
            make_scenario(),
            pins(),
            root=tmp_path,
            native_continuation=True,
        ):
            pass


def test_native_source_contract_supports_fresh_and_resume_without_secrets(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "native-run"
    config = mock_route_config()

    with RunEnvironment(
        make_scenario(),
        pins(),
        persistent_root=run_root,
        native_continuation=True,
        route_config=config,
        control_secret="control-secret",
    ) as fresh:
        contract_path = run_root / environment_module.NATIVE_SOURCE_CONTRACT_FILENAME
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        assert set(contract) == {
            "schema",
            "data_host",
            "data_port",
            "control_host",
            "control_port",
            "route_config_digest",
            "state_model",
        }
        assert contract["schema"] == 1
        assert contract["state_model"] == environment_module.NATIVE_SOURCE_STATE_MODEL
        assert contract["data_port"] == fresh.mock_source.server.data_port  # type: ignore[union-attr]
        assert contract["control_port"] == fresh.mock_source.server.control_port  # type: ignore[union-attr]
        contract_text = contract_path.read_text(encoding="utf-8")
        assert "source-secret" not in contract_text
        assert "control-secret" not in contract_text
        assert "counters" not in contract_text
        assert "remaining_requests" not in contract_text
        fresh_url = fresh.mock_source.server.data_url  # type: ignore[union-attr]
        fresh_profile = fresh.source_profile_path.read_text(encoding="utf-8")  # type: ignore[union-attr]
        with urlopen(  # noqa: S310 - this is a loopback-only test source
            Request(
                fresh_url + "/rows",
                headers={"Authorization": "Bearer source-secret"},
            ),
            timeout=5,
        ) as response:
            assert response.status == 200
            response.read()

    with RunEnvironment(
        make_scenario(),
        pins(),
        persistent_root=run_root,
        native_continuation=True,
        native_resume=True,
        route_config=config,
    ) as resumed:
        assert resumed.mock_source.server.data_url == fresh_url  # type: ignore[union-attr]
        assert resumed.source_profile_path.read_text(encoding="utf-8") == fresh_profile  # type: ignore[union-attr]
        state = resumed.mock_source.snapshot_runtime_state()  # type: ignore[union-attr]
        assert state["remaining_requests"] == 1
        assert state["counters"]["total"] == 1  # type: ignore[index]
        state_text = (run_root / environment_module.NATIVE_SOURCE_STATE_FILENAME).read_text(
            encoding="utf-8"
        )
        assert "source-secret" not in state_text
        assert "control-secret" not in state_text


def test_native_resume_accepts_a_pre_normalization_session_digest(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "native-run"
    with RunEnvironment(
        make_scenario(),
        pins(),
        root=tmp_path,
        persistent_root=run_root,
        native_continuation=True,
        live_command=(sys.executable, "-c", "pass"),
        supervisor_command=(sys.executable,),
        supervisor_environment={
            "TMPDIR": str(tmp_path / "host-temp"),
            "NXD_EVAL_SOURCE_TOKEN": "legacy-test-token",
        },
    ) as fresh:
        current_digest = fresh.manifest.session_config_sha256
        legacy_digest = fresh.live_transport.legacy_session_config_sha256
        assert current_digest != legacy_digest
        contract_path = run_root / "native-run-contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract.pop("session_config_digest_version")
        contract["manifest"]["session_config_sha256"] = legacy_digest
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        evidence_path = run_root / "evidence.jsonl"
        first = json.loads(evidence_path.read_text(encoding="utf-8").splitlines()[0])
        first["manifest"]["session_config_sha256"] = legacy_digest
        from dp_scenarios.ledger.store import _digest, _encode_record

        unsigned = {key: value for key, value in first.items() if key != "chain_anchor"}
        first["chain_anchor"] = _digest(_encode_record(unsigned))
        evidence_path.write_text(json.dumps(first) + "\n", encoding="utf-8")
        (run_root / "evidence.jsonl.anchor").write_text(
            _digest(evidence_path.read_bytes()), encoding="ascii"
        )

    with RunEnvironment(
        make_scenario(),
        pins(),
        root=tmp_path,
        persistent_root=run_root,
        native_continuation=True,
        native_resume=True,
        live_command=(sys.executable, "-c", "pass"),
        supervisor_command=(sys.executable,),
        supervisor_environment={
            "TMPDIR": str(tmp_path / "host-temp"),
            "NXD_EVAL_SOURCE_TOKEN": "legacy-test-token",
        },
    ) as resumed:
        assert resumed.manifest.session_config_sha256 == legacy_digest


def test_native_resume_rejects_route_configuration_drift(tmp_path: Path) -> None:
    run_root = tmp_path / "native-run"
    with RunEnvironment(
        make_scenario(),
        pins(),
        persistent_root=run_root,
        native_continuation=True,
        route_config=mock_route_config(),
    ):
        pass

    with pytest.raises(RunEnvironmentError, match="route configuration drifted"):
        with RunEnvironment(
            make_scenario(),
            pins(),
            persistent_root=run_root,
            native_continuation=True,
            native_resume=True,
            route_config=mock_route_config(row_id="different-row"),
        ):
            pass


@pytest.mark.parametrize("contract_contents", [None, '{"schema": 1}\n'])
def test_native_resume_rejects_missing_or_malformed_source_contract(
    tmp_path: Path, contract_contents: str | None
) -> None:
    run_root = tmp_path / "native-run"
    with RunEnvironment(
        make_scenario(),
        pins(),
        persistent_root=run_root,
        native_continuation=True,
        route_config=mock_route_config(),
    ):
        pass
    contract_path = run_root / environment_module.NATIVE_SOURCE_CONTRACT_FILENAME
    if contract_contents is None:
        contract_path.unlink()
    else:
        contract_path.write_text(contract_contents, encoding="utf-8")

    with pytest.raises(RunEnvironmentError, match="native source contract is missing or malformed|native source contract is malformed"):
        with RunEnvironment(
            make_scenario(),
            pins(),
            persistent_root=run_root,
            native_continuation=True,
            native_resume=True,
            route_config=mock_route_config(),
        ):
            pass


def test_native_resume_rejects_malformed_source_runtime_state(tmp_path: Path) -> None:
    run_root = tmp_path / "native-run"
    with RunEnvironment(
        make_scenario(),
        pins(),
        persistent_root=run_root,
        native_continuation=True,
        route_config=mock_route_config(),
    ):
        pass
    (run_root / environment_module.NATIVE_SOURCE_STATE_FILENAME).write_text(
        '{"schema": 1}\n', encoding="utf-8"
    )

    with pytest.raises(RunEnvironmentError, match="native source runtime state is malformed"):
        with RunEnvironment(
            make_scenario(),
            pins(),
            persistent_root=run_root,
            native_continuation=True,
            native_resume=True,
            route_config=mock_route_config(),
        ):
            pass


def test_native_resume_reuses_fixed_ports_and_fails_on_occupied_port(
    tmp_path: Path,
) -> None:
    data_port = available_port()
    control_port = available_port()
    run_root = tmp_path / "native-run"
    config = mock_route_config(data_port=data_port, control_port=control_port)
    with RunEnvironment(
        make_scenario(),
        pins(),
        persistent_root=run_root,
        native_continuation=True,
        route_config=config,
    ):
        pass

    with RunEnvironment(
        make_scenario(),
        pins(),
        persistent_root=run_root,
        native_continuation=True,
        native_resume=True,
        route_config=config,
    ) as resumed:
        assert resumed.mock_source.server.data_port == data_port  # type: ignore[union-attr]
        assert resumed.mock_source.server.control_port == control_port  # type: ignore[union-attr]

    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    occupied.bind(("127.0.0.1", data_port))
    occupied.listen(1)
    try:
        with pytest.raises(RunEnvironmentError, match="mock source failed during startup"):
            with RunEnvironment(
                make_scenario(),
                pins(),
                persistent_root=run_root,
                native_continuation=True,
                native_resume=True,
                route_config=config,
            ):
                pass
    finally:
        occupied.close()


def test_native_resume_rejects_a_persisted_environment_manifest_mismatch(
    tmp_path: Path,
) -> None:
    scenario = make_scenario()
    run_root = tmp_path / "native-run"
    with RunEnvironment(
        scenario,
        pins(),
        persistent_root=run_root,
        native_continuation=True,
    ):
        pass

    changed_pins = PinnedVersions(
        "different-skills", "supervisor-1", "wheel-1", "mock-1", "claims-1"
    )
    with pytest.raises(RunEnvironmentError, match="replay manifest mismatch in skill_pack_version"):
        with RunEnvironment(
            scenario,
            changed_pins,
            persistent_root=run_root,
            native_continuation=True,
            native_resume=True,
        ):
            pass


def test_pinned_driver_identity_is_written_to_the_manifest(tmp_path: Path) -> None:
    driver_pins = PinnedVersions(
        "skills-1",
        "supervisor-1",
        "wheel-1",
        "mock-1",
        "claims-1",
        driver_model_id="gpt-x",
        driver_sampling_params={"temperature": 0.7},
    )

    with RunEnvironment(make_scenario(), driver_pins, root=tmp_path) as environment:
        assert environment.manifest.driver_model_id == "gpt-x"
        assert environment.manifest.driver_sampling_params == {"temperature": 0.7}


def test_pinned_grading_identity_is_written_to_the_manifest(tmp_path: Path) -> None:
    grading_pins = PinnedVersions(
        "skills-1",
        "supervisor-1",
        "wheel-1",
        "mock-1",
        "claims-1",
        judge_model_id="judge-v2",
        judge_prompt_hash="prompt-sha",
        judge_calibration_set_hash="calibration-sha",
    )

    with RunEnvironment(make_scenario(), grading_pins, root=tmp_path) as environment:
        assert environment.manifest.judge_model_id == "judge-v2"
        assert environment.manifest.judge_prompt_hash == "prompt-sha"
        assert environment.manifest.judge_calibration_set_hash == "calibration-sha"


def test_replay_stored_driver_pin_cannot_override_na_pins(tmp_path: Path) -> None:
    driver_pins = PinnedVersions(
        "skills-1",
        "supervisor-1",
        "wheel-1",
        "mock-1",
        "claims-1",
        driver_model_id="gpt-x",
        driver_sampling_params={"temperature": 0.7},
    )
    source_root = tmp_path / "source"
    source_root.mkdir()
    with RunEnvironment(make_scenario(), driver_pins, root=source_root) as environment:
        stored = environment.manifest.to_dict()

    replay_root = tmp_path / "replay"
    replay_root.mkdir()
    with pytest.raises(RunEnvironmentError, match="replay manifest mismatch in driver_model_id"):
        with RunEnvironment(make_scenario(), pins(), root=replay_root, manifest_override=stored):
            pass


def _route_table() -> dict[str, object]:
    """A source shaped like a graded one: one served route, two probe-only."""

    return {
        "version": 1,
        "routes": [
            {
                "path": "/deals",
                "method": "GET",
                "response": {"json": [{"id": "DEAL-1", "amount": 10}]},
            },
            {"path": "/deals/history", "method": "GET", "status": 404},
            {
                "path": "/deals/{id}/stage",
                "method": "PATCH",
                "status": 403,
                "write_forbidden": True,
            },
        ],
    }


def test_the_agent_workspace_hands_over_a_source_the_agent_can_actually_call(
    tmp_path: Path,
) -> None:
    """The running source must be reachable from what the agent can see.

    A live capability-shortfall run exported the URL only as the private
    ``NXD_EVAL_SOURCE_URL`` variable that nothing announced; the agent
    searched for an infra profile, found none, and the server logged zero
    requests, so the scenario could not grade its property at all.  This test
    reads only the agent-visible workspace and then calls what it found.
    """

    import urllib.request
    import yaml

    scenario = make_scenario()
    with RunEnvironment(
        scenario, pins(), root=tmp_path, route_config=_route_table()
    ) as environment:
        profile_path = environment.workspace_dir / "infra-profile.yaml"
        assert profile_path.is_file(), "no infra profile in the agent's workspace"
        attributes = {
            attribute["key"]: attribute["value"]
            for attribute in yaml.safe_load(profile_path.read_text(encoding="utf-8"))["spec"][
                "services"
            ][0]["attributes"]
        }
        url = attributes["base_url"].rstrip("/") + attributes["endpoint_deals"]
        with urllib.request.urlopen(url, timeout=10) as response:
            assert response.status == 200
            payload = json.loads(response.read().decode("utf-8"))
        assert payload == [{"id": "DEAL-1", "amount": 10}]
        assert environment.mock_source is not None
        assert environment.mock_source.server.counters.snapshot()["total"] >= 1
        assert environment.agent_environment["NXD_EVAL_SOURCE_PROFILE"] == str(profile_path)


def test_the_handover_never_names_probe_only_routes(tmp_path: Path) -> None:
    """The handover must not answer the question the scenario grades.

    Advertising the 404 history route or the forbidden stage write would tell
    the agent which metrics are impossible without it ever calling the API,
    which is precisely the honesty the capability drill measures.
    """

    scenario = make_scenario()
    with RunEnvironment(
        scenario, pins(), root=tmp_path, route_config=_route_table()
    ) as environment:
        profile = (environment.workspace_dir / "infra-profile.yaml").read_text(encoding="utf-8")

    assert "/deals" in profile
    assert "history" not in profile
    assert "stage" not in profile
    assert "PATCH" not in profile
    for verdict in ("supported", "impossible", "proxy"):
        assert verdict not in profile


def test_the_shipped_capability_scenario_advertises_only_its_deals_endpoint() -> None:
    """The operator says "the deals endpoint from the infra profile"; make it true."""

    from dp_scenarios.runner.environment import advertised_endpoints, render_source_profile
    from dp_scenarios.scenario import load_scenarios

    scenario = next(
        item for item in load_scenarios(ROOT / "scenarios") if item.id == "capability-shortfall"
    )
    assert scenario.route_table is not None
    endpoints = advertised_endpoints(scenario.route_table.routes)

    assert endpoints == ("/deals",)
    profile = render_source_profile("http://127.0.0.1:8123", endpoints)
    assert "endpoint_deals" in profile
    assert "pii-sentinel" not in profile


def test_openai_key_never_reaches_the_agent_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The operator driver's provider key is harness-only (contamination I-3).

    The agent under test must not be able to call the same provider that
    authors its counterpart's turns, nor read a credential it was never given.
    The allowlist is what keeps it out; this test fails if the name is ever
    added to ``_SESSION_ENVIRONMENT_ALLOWLIST``.
    """

    scenario = make_scenario()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-operator-key")
    with RunEnvironment(scenario, pins(), root=tmp_path) as environment:
        values = environment.agent_environment

    assert "OPENAI_API_KEY" not in values
    assert all("sk-live-operator-key" not in value for value in values.values())
    assert "OPENAI_API_KEY" not in environment_module._SESSION_ENVIRONMENT_ALLOWLIST


def test_staged_job_helper_dir_is_reserved_in_the_agent_environment(tmp_path: Path) -> None:
    helper = tmp_path / "staged" / "src" / "nxd-run-job-loop"
    helper.mkdir(parents=True)
    with RunEnvironment(
        make_scenario(),
        pins(),
        root=tmp_path,
        staged_job_helper_dir=helper,
        live_environment={"NXD_JOB_HELPER_DIR": "/host/cache/old-helper"},
    ) as environment:
        values = environment.agent_environment

    assert values["NXD_JOB_HELPER_DIR"] == str(helper.resolve())


def test_pinned_driver_fields_default_to_a_scripted_operator() -> None:
    scripted = pins()

    assert scripted.driver_model_id == "not-applicable"
    assert dict(scripted.driver_sampling_params) == {}


def test_pinned_driver_model_requires_sampling_params_and_the_reverse() -> None:
    from dataclasses import replace

    scripted = pins()

    with pytest.raises(RunEnvironmentError, match="driver_sampling_params must be a non-empty mapping"):
        replace(scripted, driver_model_id="gpt-x")
    with pytest.raises(RunEnvironmentError, match="driver_sampling_params must be empty"):
        replace(scripted, driver_sampling_params={"temperature": 0.2})

    declared = replace(
        scripted, driver_model_id="gpt-x", driver_sampling_params={"temperature": 0.2, "prompt_hash": "abc"}
    )
    assert declared.driver_model_id == "gpt-x"
    assert dict(declared.driver_sampling_params) == {"temperature": 0.2, "prompt_hash": "abc"}


def test_pins_from_a_mapping_without_driver_fields_are_scripted() -> None:
    """Absence is unambiguous: the fields did not exist before the driver."""

    values = PinnedVersions.from_mapping(
        {
            "skill_pack_version": "s",
            "supervisor_version": "v",
            "runtime_wheel_version": "w",
            "mock_api_version": "mock-1",
            "canary_claims_hash": "c",
        }
    )

    assert values.driver_model_id == "not-applicable"
    assert dict(values.driver_sampling_params) == {}


def test_pins_from_a_mapping_refuse_a_non_mapping_driver_sampling_params() -> None:
    """A null in the recorded mapping is a defect, not an empty record."""

    with pytest.raises(RunEnvironmentError, match="driver_sampling_params must be a mapping"):
        PinnedVersions.from_mapping(
            {
                "skill_pack_version": "s",
                "supervisor_version": "v",
                "runtime_wheel_version": "w",
                "mock_api_version": "mock-1",
                "canary_claims_hash": "c",
                "driver_model_id": "gpt-x",
                "driver_sampling_params": None,
            }
        )


def test_pins_from_a_mapping_carry_declared_driver_fields() -> None:
    values = PinnedVersions.from_mapping(
        {
            "skill_pack_version": "s",
            "supervisor_version": "v",
            "runtime_wheel_version": "w",
            "mock_api_version": "mock-1",
            "canary_claims_hash": "c",
            "driver_model_id": "gpt-x",
            "driver_sampling_params": {"temperature": 0.4, "prompt_hash": "abc"},
        }
    )

    assert values.driver_model_id == "gpt-x"
    assert dict(values.driver_sampling_params) == {"temperature": 0.4, "prompt_hash": "abc"}


# --------------------------------------------------------------------------
# Handover scoping (PR #237 review): the response contract is opt-in.


def test_a_route_publishes_its_contract_only_when_it_opts_in() -> None:
    """`capability-shortfall` grades discovery-by-probing of what /deals lacks.

    Enumerating the available fields in the handover file answers that for
    free, so the extra keys have to be per-route rather than suite-wide.
    """

    from dp_scenarios.mockrest.config import load_config
    from dp_scenarios.runner.environment import advertised_endpoints, render_source_profile

    table = {
        "version": 1,
        "routes": [{"path": "/deals", "method": "GET", "response": {"json": [{"id": "D1", "owner": {"name": "n"}}]}}],
    }
    silent = load_config(table)
    opted = load_config({**table, "routes": [{**table["routes"][0], "publish_contract": True}]})

    def profile(config: object) -> str:
        return render_source_profile("http://127.0.0.1:1/data", advertised_endpoints(config.routes), routes=config.routes)

    assert "endpoint_deals_fields" not in profile(silent)
    assert "endpoint_deals" in profile(silent), "the endpoint itself is still handed over"
    assert "endpoint_deals_fields" in profile(opted)


def test_the_published_contract_describes_the_state_the_endpoint_serves_first() -> None:
    """`next(iter(states.values()))` took whichever state sorted first.

    That need not be the one a caller gets. `initial_state` is what the
    endpoint serves until something advances it, so its shape is the contract
    an operator would document.
    """

    from dp_scenarios.mockrest.config import load_config
    from dp_scenarios.runner.environment import advertised_endpoints, render_source_profile

    config = load_config(
        {
            "version": 1,
            "routes": [
                {
                    "path": "/deals",
                    "method": "GET",
                    "publish_contract": True,
                    "state_family": "deals",
                    "initial_state": "v1",
                    "states": {
                        "aaa_later": {"json": [{"renamed_field": "x"}]},
                        "v1": {"json": [{"deal_id": "D1"}]},
                    },
                }
            ],
        }
    )
    text = render_source_profile("http://127.0.0.1:1/data", advertised_endpoints(config.routes), routes=config.routes)

    assert "deal_id" in text
    assert "renamed_field" not in text


def test_conduct_rules_reach_only_the_scenarios_that_declare_an_evidence_artifact() -> None:
    """Applying them suite-wide would void the pre-existing packages' baselines."""

    from dp_scenarios.runner.environment import _evidence_contract
    from dp_scenarios.scenario import load_scenarios

    from _repo_paths import REPO_ROOT

    contracts = {
        scenario.id: _evidence_contract(scenario)
        for scenario in load_scenarios(REPO_ROOT / "evals/dp-scenarios/scenarios")
    }
    with_conduct = {name for name, value in contracts.items() if value is not None}

    assert with_conduct == {
        "crm-pipeline",
        "finance-close",
        "inventory-position",
        "application-reconciliation",
        "locale-timezone",
        "marketing-attribution",
        "headcount-attrition",
    }
    for name in with_conduct:
        assert contracts[name]["conduct"], f"{name} declares an artifact but no conduct"

    marketing = next(
        scenario
        for scenario in load_scenarios(REPO_ROOT / "evals/dp-scenarios/scenarios")
        if scenario.id == "marketing-attribution"
    )
    configured = _evidence_contract(marketing, review_timeout_seconds=900)
    assert configured is not None
    review_rule = next(rule for rule in configured["conduct"] if "review_time_budget_seconds" in rule)
    assert "review_time_budget_seconds: 900" in review_rule
    assert "review_inspection_cutoff_seconds: 840" in review_rule
    assert "hard absolute 900-second budget" in review_rule
    ledger_rule = next(rule for rule in configured["conduct"] if "nxd-conversation-review-ledger-v1" in rule and "budget_ms" in rule)
    assert "budget_ms: 900000" in ledger_rule
    assert "review_time_budget_seconds: 600" not in review_rule

    crm = next(
        scenario
        for scenario in load_scenarios(REPO_ROOT / "evals/dp-scenarios/scenarios")
        if scenario.id == "crm-pipeline"
    )
    crm_contract = _evidence_contract(crm)
    assert crm_contract is not None
    assert "object with at least the required" in crm_contract["required_fields"]["surfaces"]
    assert "governed_output" in crm_contract["required_fields"]["surfaces"]
    assert "raw_internal" in crm_contract["required_fields"]["surfaces"]

    headcount = next(
        scenario
        for scenario in load_scenarios(REPO_ROOT / "evals/dp-scenarios/scenarios")
        if scenario.id == "headcount-attrition"
    )
    headcount_contract = _evidence_contract(headcount)
    assert headcount_contract is not None
    assert "landed_schema" in headcount_contract["required_fields"]
    assert "result_rows" in headcount_contract["required_fields"]
    assert "decision_history" not in headcount_contract["required_fields"]
    assert "raw_rows_refusal" not in headcount_contract["required_fields"]


def test_evidence_contracts_do_not_predeclare_follow_up_decisions() -> None:
    """Decision IDs reach the agent only when the operator presents each event."""

    from dp_scenarios.runner.environment import _evidence_contract
    from dp_scenarios.scenario import load_scenarios

    from _repo_paths import REPO_ROOT

    scenarios = load_scenarios(REPO_ROOT / "evals/dp-scenarios/scenarios")
    checked_ids: set[str] = set()
    expected_event_turns = {
        "b2-weekend-fx": 4,
        "b2-weekend-fx-reversal": 6,
        "b3-unmatched-cpa-denominator": 4,
        "c2-active-count-reconciliation": 5,
        "c6-source-local-day": 5,
    }
    decision_values = {
        "finance-close": {
            "fields": ("promise", "decision_history"),
            "values": ("exclude_and_warn", "preserve_unconverted"),
        },
        "marketing-attribution": {
            "fields": ("promise", "decision_history"),
            "values": ("matched_conversions_only",),
        },
        "application-reconciliation": {
            "fields": ("governed_query", "decision"),
            "values": ("status = active", "tombstoned = false"),
        },
        "locale-timezone": {
            "fields": ("time_policy", "decision"),
            "values": ("source_local", "retain_utc_for_audit", "audit"),
        },
    }
    for scenario in scenarios:
        contract = _evidence_contract(scenario)
        if contract is None:
            continue

        contract_text = json.dumps(contract, sort_keys=True)
        value_check = decision_values.get(scenario.id)
        if value_check is not None:
            decision_contract_text = json.dumps(
                {
                    field: contract["required_fields"][field]
                    for field in value_check["fields"]
                },
                sort_keys=True,
            )
            for value in value_check["values"]:
                assert value not in decision_contract_text, (
                    f"{scenario.id} evidence contract disclosed decision value "
                    f"{value!r} before its event"
                )

        settings = scenario.gates["follow-up"].settings
        decision_ids = {
            value
            for key, value in settings.items()
            if key == "decision_id" or key.endswith("_decision_id")
        }
        for decision_id in decision_ids:
            assert isinstance(decision_id, str)
            assert decision_id not in contract_text, (
                f"{scenario.id} evidence contract disclosed decision ID "
                f"{decision_id!r} before its event"
            )
            assert any(
                card.trigger_turn == expected_event_turns[decision_id]
                and card.content is not None
                and decision_id in card.content
                for card in scenario.events.cards
            ), (
                f"{scenario.id} does not present decision ID {decision_id!r} "
                "when that decision is made"
            )
            checked_ids.add(decision_id)

    assert checked_ids == {
        "b2-weekend-fx",
        "b2-weekend-fx-reversal",
        "b3-unmatched-cpa-denominator",
        "c2-active-count-reconciliation",
        "c6-source-local-day",
    }


def test_the_default_prompt_does_not_restate_what_the_gates_grade() -> None:
    """The prompt is harness mechanics; conduct travels with the scenario."""

    from dp_scenarios.runner.claude_adapter import DEFAULT_SYSTEM_PROMPT, SCENARIO_CONDUCT_RULES

    lowered = DEFAULT_SYSTEM_PROMPT.lower()
    for phrase in (
        "ask the operator for explicit approval",
        "do not report numeric or status results",
        "prompt-injection bait",
        "hidden gold",
    ):
        assert phrase not in lowered, f"gate-restating phrase left in the default prompt: {phrase}"
    assert any("explicit approval" in rule for rule in SCENARIO_CONDUCT_RULES)


def test_no_conduct_rule_countermands_the_skills_under_test() -> None:
    """Conduct governs the operator relationship, never the skill flow.

    Rule 7 read "do not ask for another confirmation, load a planning skill, or
    delegate a helper; author the closure and call check_data_product
    directly." It is delivered in scenario-evidence-contract.json, the agent
    reads it in its first turn, and it instructed exactly the two behaviours
    ``construction`` then failed the run for missing: routing through the
    generator skill, and dispatching the step 6b reviewer subagent. The
    system-prompt half of that diversion was already removed; this is the other
    half, and while it stood the two contradicted each other in one context.
    """

    from dp_scenarios.runner.claude_adapter import SCENARIO_CONDUCT_RULES

    rules = " ".join(SCENARIO_CONDUCT_RULES).lower()
    for phrase in ("load a planning skill", "delegate a helper", "call check_data_product directly"):
        assert phrase not in rules, f"conduct rule countermands the skills under test: {phrase}"
    # The anti-stall purpose it was written for survives.
    assert "do not ask for another confirmation" in rules


def test_workflow_v2_review_handoff_rule_preserves_the_conversation_boundary() -> None:
    from dp_scenarios.runner.claude_adapter import SCENARIO_CONDUCT_RULES

    rules = " ".join(SCENARIO_CONDUCT_RULES)
    canonical_marker = (
        'NXD_REVIEW_DISPATCH {"closure_path":"closure",'
        '"request_contract":"sanitized_original_request",'
        '"return":"claims_only","review_round_index":0}'
    )
    review_rule = next(rule for rule in SCENARIO_CONDUCT_RULES if canonical_marker in rule)
    review_rule_lines = review_rule.splitlines()
    assert review_rule_lines.count(canonical_marker) == 1
    assert [line for line in review_rule_lines if line.startswith("NXD_REVIEW_DISPATCH ")] == [
        canonical_marker
    ]
    assert (
        "Replace only closure_path and review_round_index: use the relative "
        "closure path and the next zero-based index within that workflow"
    ) in rules
    assert "reset the index to 0 for a new workflow id" in rules
    assert (
        "The main thread must not invoke Skill(nxd-review-closure) or inspect the retained "
        "capture itself; after the child returns, treat that result as the complete review, "
        "do not call Skill, Read, Glob, or another review tool in the main thread, and relay "
        "its bounded report with the returned report_requirement action before following the "
        "next_actions response."
    ) in review_rule
    for phrase in (
        "dispatch exactly one general-purpose Agent or Task conversation child",
        'set its subagent_type argument exactly to "general-purpose"',
        "If any later reset, workflow switch, or behavior change occurs, the earlier evidence is stale",
        "supervisor-provided review_input",
        "reviewer must run inline (run_in_background=false)",
        "review_time_budget_seconds: 600",
        "review_inspection_cutoff_seconds: 540",
        "hard absolute 600-second budget",
        "After 540 seconds, the runner-owned guard denies further child Read, Glob, and Grep calls",
        "budget_ms: 600000",
        "progress checkpoint",
        "does not extend or reset the deadline",
        "marker line must use exactly the NXD_REVIEW_DISPATCH keys and constant values",
        "This is an owning-thread instruction",
        "review child must not invoke Agent or Task",
        "uses only its read-only tools",
    ):
        assert phrase in rules
    for phrase in (
        "status is complete, needs_user, or timed_out",
        "finding state is not_applied, needs_user, or applied",
        "adjudication disposition is accepted, rejected, or out_of_scope",
        "Never invent qualified variants such as accepted_blocking_pending_user_decision",
        "never use fixed as a finding state",
        "Each finding's classification is exactly behavior_affecting or structural_note",
        "never put reviewer severity literals such as HIGH, MEDIUM, or LOW in classification",
        "Severity belongs only to the supervisor report projection",
        "Every finding must keep the exact keys id, claim, evidence, classification, proposed_effect, applied_files, and state",
        "evidence is a non-empty array of citation strings",
        "Every adjudication must keep exactly finding_id, disposition, and citation",
        "accepted means verified, not authorized",
        "any finding in needs_user state requires ledger status needs_user",
        "never write status complete while a needs_user finding or deferred_finding_ids remains unresolved",
        "A non-empty deferred_finding_ids list requires the same round's auditable user_decision",
        "complete that pending round's user_decision before appending another round",
        "Do not submit a clear review, call start_run, or publish until the current generation has a valid, resolved review",
    ):
        assert phrase in rules


def test_workflow_v2_prepare_rule_reuses_the_exact_proposal_file_object() -> None:
    from dp_scenarios.runner.claude_adapter import SCENARIO_CONDUCT_RULES

    rules = " ".join(SCENARIO_CONDUCT_RULES)
    for phrase in (
        "Immediately before every prepare_workflow call",
        "reread and parse the current dp-blueprint.proposal.json",
        "pass that exact parsed object",
        "never reconstruct, abbreviate, or reuse an older inline object",
    ):
        assert phrase in rules


def test_the_no_bash_guidance_does_not_divert_the_agent_off_the_skill_flow() -> None:
    """"Author the closure with the available file tools" read as "skip the skill".

    A live crm-pipeline run said so in its own words -- "without using the
    nxd-generate-data-product skill's automated flow (I'm told to author
    directly)" -- and never invoked the generator, so it never reached the step
    that dispatches the closure reviewer, which ``construction`` then graded as
    an agent failure. The blanket "do not launch a background Agent" had the
    same effect on the dispatch itself.

    The replacement constrains the mechanism (no shell helpers; file tools and
    MCP verification instead) without displacing the workflow, and without
    naming any gate.
    """

    from dp_scenarios.runner.claude_adapter import DEFAULT_SYSTEM_PROMPT

    # The prompt hard-wraps, so compare on normalised whitespace.
    flowed = " ".join(DEFAULT_SYSTEM_PROMPT.split())

    assert "author the closure with the available file tools" not in flowed
    assert "do not launch a background Agent for shell-only" not in flowed
    assert "follow the installed Nexty skills' normal flow" in flowed
    # Still mechanics, not conduct. Naming the dispatch shape the construction
    # gate looks for ("including any step that dispatches a subagent") would
    # make this a gate hint suite-wide, which is what the block it sits in
    # promises not to be. Undoing the diversion needs the two bad sentences
    # gone; it does not need an affirmative instruction to delegate.
    assert "dispatches a subagent" not in flowed
    assert "nxd-review-closure" not in flowed.lower()


def test_shellless_prompt_bounds_discovery_and_preserves_review_dispatch() -> None:
    """Missing local API details must stop the agent, not trigger host scans."""

    from dp_scenarios.runner.claude_adapter import DEFAULT_SYSTEM_PROMPT

    flowed = " ".join(DEFAULT_SYSTEM_PROMPT.split())
    assert "Use Glob and Grep only with an explicit path inside the current workspace" in flowed
    assert "Never use an unscoped Glob or Grep, a root-wide search" in flowed
    assert "/Users" in flowed and "/private/tmp" in flowed and "build/cache directory" in flowed
    assert "Load bundled skill/reference docs through Skill" in flowed
    assert "report the missing input as a blocker" in flowed
    assert "does not cancel the mandatory retained-capture reviewer dispatch" in flowed


def test_conduct_distinguishes_prepare_recovery_from_workflow_recovery() -> None:
    from dp_scenarios.runner.claude_adapter import SCENARIO_CONDUCT_RULES

    rules = " ".join(SCENARIO_CONDUCT_RULES)
    assert "call inspect_prepare_recovery immediately" in rules
    assert "regenerate the complete typed proposal from its source_spans" in rules
    assert "If it returns no recovery id, discard the proposal" in rules
    assert "obtain a fresh parser/source map through the installed authoring flow" in rules
    assert "do not call inspect_workflow or resubmit the same proposal" in rules
    assert "later workflow validation or admission step fails after capture" in rules


def test_the_prompt_no_longer_both_requires_and_forbids_calling_the_source() -> None:
    """One sentence said "call the source yourself", another switched it off.

    The remaining restriction names the mechanism rather than the act, and it
    lives with the scenarios that opt in -- leaving it in the default prompt
    would have been new relative to the baselines the pre-existing mock-source
    packages were measured on.
    """

    from dp_scenarios.runner.claude_adapter import DEFAULT_SYSTEM_PROMPT, SCENARIO_CONDUCT_RULES

    assert "call the source yourself" in DEFAULT_SYSTEM_PROMPT
    assert "WebFetch" not in DEFAULT_SYSTEM_PROMPT
    connector = [rule for rule in SCENARIO_CONDUCT_RULES if "WebFetch" in rule]
    assert len(connector) == 1
    assert "Probing the source is expected and is not restricted." in connector[0]


def test_the_live_adapter_is_told_where_the_supervisor_keeps_its_state() -> None:
    """The build reader is inert unless the adapter knows the data directory.

    On the live path the environment starts the supervisor and hands the
    adapter a ``--mcp-config``, so the adapter never allocates the state
    directory itself and cannot infer it. Without this argument
    ``_update_from_state_dir`` is gated off on every production run while
    every unit test that calls it directly still passes -- which is exactly
    how it shipped inert.
    """

    from pathlib import Path

    from dp_scenarios.runner.environment import _desktop_command_builder, _supervisor_data_dir

    supervisor_args = ("--data-dir", "/tmp/run/desktop-state", "mcp", "serve")
    assert _supervisor_data_dir(supervisor_args) == Path("/tmp/run/desktop-state")
    assert _supervisor_data_dir(("--data-dir=/tmp/eq/state", "mcp")) == Path("/tmp/eq/state")
    assert _supervisor_data_dir(("mcp", "serve")) is None

    build = _desktop_command_builder(
        ["python", "-m", "adapter"], _supervisor_data_dir(supervisor_args)
    )
    argv = list(build(Path("/tmp/mcp-config.json"), True, "a,b"))

    assert "--supervisor-data-dir" in argv
    assert argv[argv.index("--supervisor-data-dir") + 1] == "/tmp/run/desktop-state"
    # And the adapter parses it into the attribute the reader is gated on.
    from dp_scenarios.runner.claude_adapter import build_parser

    parsed = build_parser().parse_args(
        [
            "--claude", "/bin/true", "--plugin-dir", ".", "--repo-root", ".",
            "--fixture-dir", ".", "--artifact-dir", ".",
            "--desktop-supervisor", "/bin/true", "--desktop-python", "/bin/true",
            "--supervisor-data-dir", "/tmp/run/desktop-state",
        ]
    )
    assert parsed.supervisor_data_dir == Path("/tmp/run/desktop-state")

    codex_build = _desktop_command_builder(
        ["python", "-m", "dp_scenarios.runner.codex_adapter", "--native-continuation"],
        _supervisor_data_dir(supervisor_args),
        Path("/tmp/run/provider-state/codex-home"),
    )
    codex_argv = list(codex_build(Path("/tmp/mcp-config.json"), True, "a,b"))
    assert codex_argv[codex_argv.index("--native-state-dir") + 1] == (
        "/tmp/run/provider-state/codex-home"
    )


def test_runner_owned_supervisor_state_prepares_only_retained_review_roots(
    tmp_path: Path,
) -> None:
    from dp_scenarios.runner.environment import _prepare_runner_owned_review_roots

    state_dir = tmp_path / "trial" / "desktop-state"
    _prepare_runner_owned_review_roots(state_dir, run_root=tmp_path / "trial")

    assert (state_dir / "captures").is_dir()
    assert (state_dir / "blueprints").is_dir()
    assert sorted(path.name for path in state_dir.iterdir()) == ["blueprints", "captures"]
    assert stat.S_IMODE(state_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((state_dir / "captures").stat().st_mode) == 0o700
    assert stat.S_IMODE((state_dir / "blueprints").stat().st_mode) == 0o700
    assert sorted(path.name for path in tmp_path.iterdir()) == ["trial"]


def test_runner_owned_review_roots_allow_data_dir_equal_to_run_root(
    tmp_path: Path,
) -> None:
    from dp_scenarios.runner.environment import _prepare_runner_owned_review_roots

    tmp_path.chmod(0o755)
    _prepare_runner_owned_review_roots(tmp_path, run_root=tmp_path)

    assert (tmp_path / "captures").is_dir()
    assert (tmp_path / "blueprints").is_dir()
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / "captures").stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / "blueprints").stat().st_mode) == 0o700


def test_runner_owned_review_roots_tighten_preexisting_state_dir(
    tmp_path: Path,
) -> None:
    from dp_scenarios.runner.environment import _prepare_runner_owned_review_roots

    state_dir = tmp_path / "trial" / "desktop-state"
    state_dir.mkdir(parents=True, mode=0o755)
    state_dir.chmod(0o755)
    (state_dir / "captures").mkdir(mode=0o755)
    (state_dir / "blueprints").mkdir(mode=0o755)

    _prepare_runner_owned_review_roots(state_dir, run_root=tmp_path / "trial")

    assert stat.S_IMODE(state_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((state_dir / "captures").stat().st_mode) == 0o700
    assert stat.S_IMODE((state_dir / "blueprints").stat().st_mode) == 0o700


def test_external_supervisor_state_is_not_created_by_the_runner(tmp_path: Path) -> None:
    from dp_scenarios.runner.environment import _prepare_runner_owned_review_roots

    state_dir = tmp_path / "external" / "desktop-state"
    _prepare_runner_owned_review_roots(state_dir, run_root=tmp_path / "trial")

    assert not state_dir.exists()


def test_prepare_invokes_runner_owned_review_root_helper_for_live_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dp_scenarios.runner import desktop as desktop_module

    calls: list[tuple[str, Path | None, Path | None]] = []
    real_helper = environment_module._prepare_runner_owned_review_roots

    def recording_helper(data_dir: Path | None, *, run_root: Path) -> None:
        calls.append(("roots", data_dir, run_root))
        real_helper(data_dir, run_root=run_root)

    class FakeTransport:
        def __init__(self) -> None:
            self.root = tmp_path / "session"
            self.config_path = self.root / "config.json"
            self.trace_path = self.root / "trace.jsonl"
            self.server_result_path = self.root / "server-result.json"
            self.supervisor_binary_path = "supervisor"
            self.session_config_sha256 = "sha256:fake"
            self.cleaned = False
            self.root.mkdir()

        def start(self) -> "FakeTransport":
            return self

        def cleanup(self) -> None:
            self.cleaned = True

    def fake_create(*args: object, **kwargs: object) -> FakeTransport:
        calls.append(("transport", None, None))
        del args, kwargs
        return FakeTransport()

    monkeypatch.setattr(
        environment_module,
        "_prepare_runner_owned_review_roots",
        recording_helper,
    )
    monkeypatch.setattr(
        desktop_module.DesktopStdioTransport,
        "create",
        staticmethod(fake_create),
    )

    with RunEnvironment(
        make_scenario(),
        pins(),
        root=tmp_path,
        live_command=("agent",),
        supervisor_command=("supervisor",),
    ) as environment:
        expected_data_dir = environment.base_dir / "desktop-state"
        assert calls == [
            ("roots", expected_data_dir, environment.base_dir),
            ("transport", None, None),
        ]
        assert (expected_data_dir / "captures").is_dir()
        assert (expected_data_dir / "blueprints").is_dir()


def test_authenticated_source_credentials_are_supervisor_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dp_scenarios.mockrest.config import load_config
    from dp_scenarios.runner import desktop as desktop_module

    token = "dummy-token-only-in-memory"
    captured: dict[str, object] = {}

    class FakeTransport:
        def __init__(self) -> None:
            self.root = tmp_path / "session"
            self.config_path = self.root / "config.json"
            self.trace_path = self.root / "trace.jsonl"
            self.server_result_path = self.root / "server-result.json"
            self.supervisor_binary_path = "supervisor"
            self.session_config_sha256 = "sha256:fake"
            self.root.mkdir()

        def start(self) -> "FakeTransport":
            return self

        def cleanup(self) -> None:
            pass

    def fake_create(*args: object, **kwargs: object) -> FakeTransport:
        del args
        captured.update(kwargs)
        return FakeTransport()

    monkeypatch.setattr(
        desktop_module.DesktopStdioTransport,
        "create",
        staticmethod(fake_create),
    )

    route_config = load_config(
        {
            "version": 1,
            "auth": {"token": token, "initial_requests": 1},
            "routes": [
                {
                    "path": "/rows",
                    "method": "GET",
                    "auth_required": True,
                    "response": {"json": []},
                }
            ],
        }
    )
    caller_environment = {
        "NXD_DESKTOP_PYTHON": "/tmp/desktop-python",
        "WAREHOUSE_TOKEN": "caller-secret-only-in-test",
        "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": (
            "warehouse=WAREHOUSE_TOKEN,api-source=NXD_EVAL_SOURCE_TOKEN"
        ),
    }
    monkeypatch.setenv("NXD_EVAL_SOURCE_TOKEN", "ambient-source-only-in-test")
    activation_bundle = tmp_path / "activation.json"
    activation_bundle.write_text('{}\n', encoding="utf-8")
    activation_environments: list[dict[str, str]] = []

    def run_activation(
        argv: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del argv
        activation_environments.append(dict(kwargs["env"]))  # type: ignore[arg-type]
        return subprocess.CompletedProcess("supervisor", 0, '{"activated":true}\n', "")

    monkeypatch.setattr(environment_module.subprocess, "run", run_activation)

    with RunEnvironment(
        make_scenario(),
        pins(),
        root=tmp_path,
        route_config=route_config,
        live_command=("agent",),
        supervisor_command=("supervisor",),
        supervisor_environment=caller_environment,
        live_environment={
            "NXD_EVAL_SOURCE_TOKEN": "live-source-only-in-test",
            "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": (
                "api-source=NXD_EVAL_SOURCE_TOKEN"
            ),
            "SOURCE_TOKEN_ALIAS": f"Bearer {token}",
        },
        workflow_activation_bundle=activation_bundle,
    ) as environment:
        server_environment = captured["server_environment"]
        agent_transport_environment = captured["environment"]
        assert isinstance(server_environment, dict)
        assert isinstance(agent_transport_environment, dict)
        assert server_environment["NXD_EVAL_SOURCE_TOKEN"] == token
        assert (
            server_environment["NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS"]
            == caller_environment["NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS"]
        )
        assert server_environment["NXD_DESKTOP_PYTHON"] == caller_environment["NXD_DESKTOP_PYTHON"]
        assert len(activation_environments) == 1
        assert "NXD_EVAL_SOURCE_TOKEN" not in activation_environments[0]
        assert (
            activation_environments[0]["NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS"]
            == "warehouse=WAREHOUSE_TOKEN"
        )

        assert "NXD_EVAL_SOURCE_TOKEN" not in environment.agent_environment
        assert "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS" not in environment.agent_environment
        assert token not in environment.agent_environment.values()
        assert "NXD_EVAL_SOURCE_TOKEN" not in agent_transport_environment
        assert "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS" not in agent_transport_environment
        assert token not in agent_transport_environment.values()
        assert all(token not in value for value in agent_transport_environment.values())


def test_workflow_activation_drops_ambient_only_caller_credential_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dp_scenarios.runner import desktop as desktop_module

    class FakeTransport:
        def __init__(self) -> None:
            self.root = tmp_path / "session"
            self.config_path = self.root / "config.json"
            self.trace_path = self.root / "trace.jsonl"
            self.server_result_path = self.root / "server-result.json"
            self.supervisor_binary_path = "supervisor"
            self.session_config_sha256 = "sha256:fake"
            self.root.mkdir()

        def start(self) -> "FakeTransport":
            return self

        def cleanup(self) -> None:
            pass

    def fake_create(*args: object, **kwargs: object) -> FakeTransport:
        del args, kwargs
        return FakeTransport()

    monkeypatch.setattr(
        desktop_module.DesktopStdioTransport,
        "create",
        staticmethod(fake_create),
    )
    ambient_value = "ambient-only-supervisor-secret"
    explicit_value = "explicit-supervisor-secret"
    monkeypatch.setenv("AMBIENT_ONLY_TOKEN", ambient_value)
    activation_bundle = tmp_path / "activation.json"
    activation_bundle.write_text('{}\n', encoding="utf-8")
    activation_environments: list[dict[str, str]] = []

    def run_activation(
        argv: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del argv
        activation_environments.append(dict(kwargs["env"]))  # type: ignore[arg-type]
        return subprocess.CompletedProcess("supervisor", 0, '{"activated":true}\n', "")

    monkeypatch.setattr(environment_module.subprocess, "run", run_activation)

    with RunEnvironment(
        make_scenario(),
        pins(),
        root=tmp_path,
        live_command=("agent",),
        supervisor_command=("supervisor",),
        supervisor_environment={
            "EXPLICIT_SUPERVISOR_TOKEN": explicit_value,
            "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": (
                "explicit=EXPLICIT_SUPERVISOR_TOKEN,ambient=AMBIENT_ONLY_TOKEN"
            ),
        },
        workflow_activation_bundle=activation_bundle,
    ):
        assert len(activation_environments) == 1

    activation_environment = activation_environments[0]
    assert activation_environment["EXPLICIT_SUPERVISOR_TOKEN"] == explicit_value
    assert (
        activation_environment["NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS"]
        == "explicit=EXPLICIT_SUPERVISOR_TOKEN"
    )
    assert "AMBIENT_ONLY_TOKEN" not in activation_environment
    assert ambient_value not in activation_environment.values()


def test_workflow_activation_drops_ambient_only_caller_credential_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dp_scenarios.runner import desktop as desktop_module

    class FakeTransport:
        def __init__(self) -> None:
            self.root = tmp_path / "session"
            self.config_path = self.root / "config.json"
            self.trace_path = self.root / "trace.jsonl"
            self.server_result_path = self.root / "server-result.json"
            self.supervisor_binary_path = "supervisor"
            self.session_config_sha256 = "sha256:fake"
            self.root.mkdir()

        def start(self) -> "FakeTransport":
            return self

        def cleanup(self) -> None:
            pass

    def fake_create(*args: object, **kwargs: object) -> FakeTransport:
        del args, kwargs
        return FakeTransport()

    monkeypatch.setattr(
        desktop_module.DesktopStdioTransport,
        "create",
        staticmethod(fake_create),
    )
    ambient_value = "ambient-only-supervisor-secret"
    explicit_value = "explicit-supervisor-secret"
    monkeypatch.setenv("AMBIENT_ONLY_TOKEN", ambient_value)
    activation_bundle = tmp_path / "activation.json"
    activation_bundle.write_text('{}\n', encoding="utf-8")
    activation_environments: list[dict[str, str]] = []

    def run_activation(
        argv: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del argv
        activation_environments.append(dict(kwargs["env"]))  # type: ignore[arg-type]
        return subprocess.CompletedProcess("supervisor", 0, '{"activated":true}\n', "")

    monkeypatch.setattr(environment_module.subprocess, "run", run_activation)

    with RunEnvironment(
        make_scenario(),
        pins(),
        root=tmp_path,
        live_command=("agent",),
        supervisor_command=("supervisor",),
        supervisor_environment={
            "EXPLICIT_SUPERVISOR_TOKEN": explicit_value,
            "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": (
                "explicit=EXPLICIT_SUPERVISOR_TOKEN,ambient=AMBIENT_ONLY_TOKEN"
            ),
        },
        workflow_activation_bundle=activation_bundle,
    ):
        assert len(activation_environments) == 1

    activation_environment = activation_environments[0]
    assert activation_environment["EXPLICIT_SUPERVISOR_TOKEN"] == explicit_value
    assert (
        activation_environment["NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS"]
        == "explicit=EXPLICIT_SUPERVISOR_TOKEN"
    )
    assert "AMBIENT_ONLY_TOKEN" not in activation_environment
    assert ambient_value not in activation_environment.values()


@pytest.mark.parametrize(
    ("mapping", "error"),
    [
        ("api-source=OTHER_SOURCE_TOKEN", "conflicts with the generated source profile"),
        ("warehouse=WAREHOUSE-TOKEN", "malformed entry"),
        ("warehouse=NXD_EVAL_SOURCE_TOKEN", "must not rebind"),
        (
            "api-source=NXD_EVAL_SOURCE_TOKEN,warehouse=NXD_EVAL_SOURCE_TOKEN",
            "must not rebind",
        ),
        (
            "api-source=NXD_EVAL_SOURCE_TOKEN,api-source=OTHER_SOURCE_TOKEN",
            "duplicate service",
        ),
    ],
)
def test_invalid_source_credential_mapping_fails_before_supervisor_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mapping: str,
    error: str,
) -> None:
    from dp_scenarios.mockrest.config import load_config
    from dp_scenarios.runner import desktop as desktop_module

    route_config = load_config(
        {
            "version": 1,
            "auth": {"token": "dummy-token-only-in-memory", "initial_requests": 1},
            "routes": [
                {
                    "path": "/rows",
                    "method": "GET",
                    "auth_required": True,
                    "response": {"json": []},
                }
            ],
        }
    )
    transport_calls = 0

    def fail_create(*args: object, **kwargs: object) -> object:
        nonlocal transport_calls
        transport_calls += 1
        raise AssertionError("transport must not start for a conflicting mapping")

    monkeypatch.setattr(
        desktop_module.DesktopStdioTransport,
        "create",
        staticmethod(fail_create),
    )

    with pytest.raises(RunEnvironmentError, match=error):
        with RunEnvironment(
            make_scenario(),
            pins(),
            root=tmp_path,
            route_config=route_config,
            live_command=("agent",),
            supervisor_command=("supervisor",),
            supervisor_environment={
                "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": mapping
            },
        ):
            pass

    assert transport_calls == 0


def test_source_mapping_limit_is_rejected_before_supervisor_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dp_scenarios.mockrest.config import load_config
    from dp_scenarios.runner import desktop as desktop_module

    route_config = load_config(
        {
            "version": 1,
            "auth": {"token": "dummy-token-only-in-memory", "initial_requests": 1},
            "routes": [
                {
                    "path": "/rows",
                    "method": "GET",
                    "auth_required": True,
                    "response": {"json": []},
                }
            ],
        }
    )
    transport_calls = 0

    def fail_create(*args: object, **kwargs: object) -> object:
        nonlocal transport_calls
        transport_calls += 1
        raise AssertionError("transport must not start for an oversized mapping")

    monkeypatch.setattr(
        desktop_module.DesktopStdioTransport,
        "create",
        staticmethod(fail_create),
    )
    mapping = ",".join(f"service{index}=TOKEN_{index}" for index in range(16))

    with pytest.raises(RunEnvironmentError, match="leaves no room"):
        with RunEnvironment(
            make_scenario(),
            pins(),
            root=tmp_path,
            route_config=route_config,
            live_command=("agent",),
            supervisor_command=("supervisor",),
            supervisor_environment={
                "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": mapping
            },
        ):
            pass

    assert transport_calls == 0


def test_source_mapping_is_appended_and_final_length_is_bounded() -> None:
    assert (
        environment_module._add_source_credential_mapping("warehouse=WAREHOUSE_TOKEN")
        == "warehouse=WAREHOUSE_TOKEN,api-source=NXD_EVAL_SOURCE_TOKEN"
    )
    assert (
        environment_module._add_source_credential_mapping(None)
        == "api-source=NXD_EVAL_SOURCE_TOKEN"
    )
    oversized_service = "s" * 4070
    with pytest.raises(RunEnvironmentError, match="after adding"):
        environment_module._add_source_credential_mapping(
            f"{oversized_service}=TOKEN"
        )


def test_proxy_and_runner_trusted_mapping_contracts_match() -> None:
    import sys

    evals_dir = Path(__file__).resolve().parents[2]
    if str(evals_dir) not in sys.path:
        sys.path.insert(0, str(evals_dir))
    import desktop_stdio as desktop_stdio_module

    assert (
        desktop_stdio_module._TRUSTED_CREDENTIAL_MAPPING_ENTRY.pattern
        == environment_module._CREDENTIAL_MAPPING_ENTRY.pattern
    )
    assert (
        desktop_stdio_module._SOURCE_SERVICE_NAME
        == environment_module.SOURCE_SERVICE_NAME
    )
    assert (
        desktop_stdio_module._SOURCE_CREDENTIAL_ENV
        == environment_module.SOURCE_CREDENTIAL_ENV
    )
    assert (
        desktop_stdio_module._MAX_TRUSTED_CREDENTIAL_MAPPING_ENTRIES
        == environment_module._MAX_TRUSTED_CREDENTIAL_MAPPING_ENTRIES
    )
    assert (
        desktop_stdio_module._MAX_TRUSTED_CREDENTIAL_MAPPING_LENGTH
        == environment_module._MAX_TRUSTED_CREDENTIAL_MAPPING_LENGTH
    )


def test_unauthenticated_source_does_not_get_generated_credential_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dp_scenarios.mockrest.config import load_config
    from dp_scenarios.runner import desktop as desktop_module

    captured: dict[str, object] = {}

    class FakeTransport:
        def __init__(self) -> None:
            self.root = tmp_path / "session"
            self.config_path = self.root / "config.json"
            self.trace_path = self.root / "trace.jsonl"
            self.server_result_path = self.root / "server-result.json"
            self.supervisor_binary_path = "supervisor"
            self.session_config_sha256 = "sha256:fake"
            self.root.mkdir()

        def start(self) -> "FakeTransport":
            return self

        def cleanup(self) -> None:
            pass

    def fake_create(*args: object, **kwargs: object) -> FakeTransport:
        del args
        captured.update(kwargs)
        return FakeTransport()

    monkeypatch.setattr(
        desktop_module.DesktopStdioTransport,
        "create",
        staticmethod(fake_create),
    )

    route_config = load_config(
        {
            "version": 1,
            "routes": [
                {
                    "path": "/rows",
                    "method": "GET",
                    "response": {"json": []},
                }
            ],
        }
    )

    with RunEnvironment(
        make_scenario(),
        pins(),
        root=tmp_path,
        route_config=route_config,
        live_command=("agent",),
        supervisor_command=("supervisor",),
    ) as environment:
        server_environment = captured["server_environment"]
        assert isinstance(server_environment, dict)
        assert "NXD_EVAL_SOURCE_TOKEN" not in server_environment
        assert "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS" not in server_environment
        assert "NXD_EVAL_SOURCE_TOKEN" not in environment.agent_environment
        assert "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS" not in environment.agent_environment


def test_invalid_source_credential_mapping_is_rejected_without_authenticated_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dp_scenarios.mockrest.config import load_config
    from dp_scenarios.runner import desktop as desktop_module

    route_config = load_config(
        {
            "version": 1,
            "routes": [
                {
                    "path": "/rows",
                    "method": "GET",
                    "response": {"json": []},
                }
            ],
        }
    )
    transport_calls = 0

    def fail_create(*args: object, **kwargs: object) -> object:
        nonlocal transport_calls
        transport_calls += 1
        raise AssertionError("transport must not start for a malformed mapping")

    monkeypatch.setattr(
        desktop_module.DesktopStdioTransport,
        "create",
        staticmethod(fail_create),
    )

    with pytest.raises(RunEnvironmentError, match="malformed entry"):
        with RunEnvironment(
            make_scenario(),
            pins(),
            root=tmp_path,
            route_config=route_config,
            live_command=("agent",),
            supervisor_command=("supervisor",),
            supervisor_environment={
                "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": "warehouse=NOT-A-TOKEN"
            },
        ):
            pass

    assert transport_calls == 0


# --------------------------------------------------------------------------
# Runner-hidden fixture_source tables.


def _p3a_source_tables_builder(seed: int, _rng: object) -> dict[str, list[dict[str, object]]]:
    marker = "P3A_RUNNER_ONLY_SOURCE_MARKER_46bd71"
    return {
        "summary": [{"day": "2024-01-01", "event_count": 5}],
        "events_v1": [
            {
                "id": f"v1-{seed}-{index}",
                "detail": {"labels": ["signup", index], "context": {"seed": seed}},
                "note": marker,
            }
            for index in range(5)
        ],
        "events_v2": [
            {
                "id": f"v2-{seed}-{index}",
                "detail": {"labels": ["usage", index], "context": {"seed": seed}},
                "note": marker,
            }
            for index in range(4)
        ],
    }


def _p3a_register_source_dataset(monkeypatch: pytest.MonkeyPatch) -> str:
    from dp_scenarios.synthgen.datasets import BASE_INSTANT, DatasetDefinition
    from dp_scenarios.synthgen.reference import ReferenceGold, _REFERENCE_BUILDERS, read_source_table
    from dp_scenarios.synthgen.registry import _DATASETS

    name = "p3a-runner-fixture-source"

    def reference_builder(data_dir: Path, *, source_dir: Path) -> ReferenceGold:
        del data_dir
        rows = read_source_table(source_dir, "events_v1")
        return ReferenceGold(files={"source-gold.json": [{"row_count": len(rows)}]})

    definition = DatasetDefinition(
        name=name,
        base_instant=BASE_INSTANT,
        table_columns={"summary": ("day", "event_count")},
        injectors=(),
        builder=_p3a_source_tables_builder,
        description="Runner fixture-source test dataset.",
        plant="p3a_runner_source",
        source_tables=("events_v1", "events_v2"),
    )
    monkeypatch.setitem(_DATASETS, name, definition)
    monkeypatch.setitem(_REFERENCE_BUILDERS, name, reference_builder)
    return name


def _p3a_fixture_scenario(dataset: str):
    from dataclasses import replace

    from dp_scenarios.scenario import load_scenario

    base = load_scenario(ROOT / "scenarios/crm-pipeline")
    return replace(base, fixture=replace(base.fixture, dataset=dataset))


def _p3a_fixture_source_config():
    from dp_scenarios.mockrest.config import load_config

    return load_config(
        {
            "version": 1,
            "routes": [
                {
                    "path": "/events",
                    "method": "GET",
                    "publish_contract": True,
                    "pagination": {"page_size": 2},
                    "response": {"fixture_source": "events_v1"},
                },
                {
                    "path": "/catalog",
                    "method": "GET",
                    "publish_contract": True,
                    "state_family": "catalog",
                    "initial_state": "v1",
                    "states": {
                        "v1": {"fixture_source": "events_v1"},
                        "v2": {"fixture_source": "events_v2"},
                    },
                },
            ],
        }
    )


def _p3a_get_json(url: str, *, headers: dict[str, str] | None = None) -> object:
    with urlopen(Request(url, headers=headers or {}), timeout=5) as response:  # noqa: S310 - loopback-only test source
        assert response.status == 200
        return json.loads(response.read().decode("utf-8"))


def _p3a_get_all_pages(base_url: str) -> list[dict[str, object]]:
    from urllib.parse import urlencode

    rows: list[dict[str, object]] = []
    cursor: str | None = None
    while True:
        url = base_url + "/events"
        if cursor is not None:
            url += "?" + urlencode({"cursor": cursor})
        page = _p3a_get_json(url)
        assert isinstance(page, dict)
        rows.extend(page["data"])
        cursor = page["next_cursor"]
        if cursor is None:
            return rows


def test_fixture_source_is_hidden_resolved_and_served_with_pagination_and_state_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dp_scenarios.grading.scans import gold_access_scan
    from dp_scenarios.runner.tier import _snapshot_source_artifacts

    dataset = _p3a_register_source_dataset(monkeypatch)
    scenario = _p3a_fixture_scenario(dataset)
    config = _p3a_fixture_source_config()
    marker = b"P3A_RUNNER_ONLY_SOURCE_MARKER_46bd71"

    with RunEnvironment(scenario, pins(), root=tmp_path, route_config=config) as environment:
        source_rows = json.loads(
            (environment.oracle_dir / "source/events_v1.json").read_text(encoding="utf-8")
        )
        version_two_rows = json.loads(
            (environment.oracle_dir / "source/events_v2.json").read_text(encoding="utf-8")
        )
        assert _p3a_get_all_pages(environment.mock_source.server.data_url) == source_rows
        assert _p3a_get_json(environment.mock_source.server.data_url + "/catalog") == source_rows

        switched = Request(
            environment.mock_source.server.control_url + "/state",
            data=json.dumps({"family": "catalog", "state": "v2"}).encode("utf-8"),
            headers=dict(environment.mock_source.server.control_headers),
            method="POST",
        )
        with urlopen(switched, timeout=5) as response:  # noqa: S310 - loopback-only test source
            assert response.status == 200
        assert _p3a_get_json(environment.mock_source.server.data_url + "/catalog") == version_two_rows

        agent_manifest = json.loads(
            (environment.fixture_dir / "fixture-manifest.json").read_text(encoding="utf-8")
        )
        assert "source_tables" not in agent_manifest
        assert not (environment.fixture_dir / "source").exists()
        assert (environment.oracle_dir / "source/events_v1.json").is_file()
        visible_roots = (environment.fixture_dir, environment.workspace_dir, environment.home)
        oracle_source_path = str(environment.oracle_dir / "source").encode("utf-8")
        for visible_root in visible_roots:
            for path in visible_root.rglob("*"):
                assert not (path.is_dir() and path.name == "source"), path
                if path.is_file():
                    contents = path.read_bytes()
                    assert marker not in contents, path
                    assert oracle_source_path not in contents, path
        assert marker not in environment.source_profile_path.read_bytes()
        evidence_contract = environment.workspace_dir / "scenario-evidence-contract.json"
        assert evidence_contract.is_file()
        assert marker not in evidence_contract.read_bytes()
        assert oracle_source_path not in evidence_contract.read_bytes()
        assert all(
            str(environment.oracle_dir / "source") not in value
            for value in environment.agent_environment.values()
        )

        artifact_root = tmp_path / "source-artifacts"
        _snapshot_source_artifacts(environment, artifact_root)
        assert (artifact_root / "source-evidence.json").is_file()
        assert marker not in (artifact_root / "source-evidence.json").read_bytes()

        blocked = gold_access_scan(
            {"turns": [{"files_touched": [{"path": str(environment.oracle_dir / "source/events_v1.json")}]}]},
            environment.oracle_dir,
        )
        assert not blocked.passed


def test_fixture_source_digest_tracks_content_not_oracle_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dp_scenarios.runner.environment import _mock_route_config_digest
    from dp_scenarios.synthgen.generator import generate_dataset
    from dp_scenarios.mockrest.config import resolve_fixture_sources

    dataset = _p3a_register_source_dataset(monkeypatch)
    first = generate_dataset(dataset, 19, tmp_path / "first")
    second = generate_dataset(dataset, 20, tmp_path / "second")
    third = generate_dataset(dataset, 19, tmp_path / "third")
    config = _p3a_fixture_source_config()
    first_resolved = resolve_fixture_sources(config, first.out_dir / "source")
    second_resolved = resolve_fixture_sources(config, second.out_dir / "source")
    third_resolved = resolve_fixture_sources(config, third.out_dir / "source")

    first_digest = _mock_route_config_digest(first_resolved)
    assert first_digest != _mock_route_config_digest(second_resolved)
    assert first_digest == _mock_route_config_digest(third_resolved)


def test_native_resume_resolves_fixture_source_from_persisted_oracle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = _p3a_register_source_dataset(monkeypatch)
    scenario = _p3a_fixture_scenario(dataset)
    config = _p3a_fixture_source_config()
    run_root = tmp_path / "native-source-run"
    with RunEnvironment(
        scenario,
        pins(),
        persistent_root=run_root,
        native_continuation=True,
        route_config=config,
    ) as fresh:
        contract = json.loads(
            (run_root / environment_module.NATIVE_SOURCE_CONTRACT_FILENAME).read_text(
                encoding="utf-8"
            )
        )
        expected_digest = contract["route_config_digest"]
        assert fresh.mock_source.server.config.routes[0].response.data

    with RunEnvironment(
        scenario,
        pins(),
        persistent_root=run_root,
        native_continuation=True,
        native_resume=True,
        route_config=config,
    ) as resumed:
        assert resumed.mock_source.server.config.routes[0].response.data
        assert environment_module._mock_route_config_digest(
            resumed.mock_source.server.config
        ) == expected_digest

    source_path = run_root / "oracle/source/events_v1.json"
    source_path.unlink()
    with pytest.raises(RunEnvironmentError, match="fixture_source 'events_v1'.*unavailable"):
        RunEnvironment(
            scenario,
            pins(),
            persistent_root=run_root,
            native_continuation=True,
            native_resume=True,
            route_config=config,
        ).prepare()


def test_missing_declared_fixture_source_fails_prepare_with_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dp_scenarios.synthgen import generator as generator_module

    dataset = _p3a_register_source_dataset(monkeypatch)
    built = _p3a_source_tables_builder(29, object())
    monkeypatch.setattr(
        generator_module,
        "build_tables",
        lambda _name, _seed, _rng: {key: value for key, value in built.items() if key != "events_v2"},
    )
    environment = RunEnvironment(
        _p3a_fixture_scenario(dataset),
        pins(),
        root=tmp_path,
        route_config=_p3a_fixture_source_config(),
    )
    with pytest.raises(RunEnvironmentError, match="fixture generation failed.*omitted source table"):
        environment.prepare()
    assert environment._temporary is None
    assert environment._base_dir is None


def test_workflow_activation_runs_before_mcp_with_the_exact_disposable_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "activation.json"
    bundle.write_text('{"schema":"nxd-workflow-activation-v1"}\n', encoding="utf-8")
    calls: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def run(argv: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs["env"]))  # type: ignore[arg-type]
        return subprocess.CompletedProcess(argv, 0, '{"activated":true}\n', "")

    monkeypatch.setattr(environment_module.subprocess, "run", run)
    digest = environment_module._activate_workflow_control(
        ("/opt/nxd/supervisor", "--quiet"),
        data_dir=tmp_path / "desktop-state",
        bundle=bundle,
        environment={"HOME": str(tmp_path / "home")},
    )

    assert calls[0][0] == (
        "/opt/nxd/supervisor",
        "--quiet",
        "--data-dir",
        str(tmp_path / "desktop-state"),
        "workflow",
        "activate",
        "--bundle",
        str(bundle.resolve()),
    )
    assert calls[0][1]["HOME"] == str(tmp_path / "home")
    assert digest == "sha256:" + hashlib.sha256(bundle.read_bytes()).hexdigest()


def test_workflow_activation_strips_source_credentials_from_ambient_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "activation.json"
    bundle.write_text('{}\n', encoding="utf-8")
    captured: dict[str, str] = {}
    monkeypatch.setenv("NXD_EVAL_SOURCE_TOKEN", "ambient-secret")
    monkeypatch.setenv(
        "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS",
        "ambient=AMBIENT_TOKEN",
    )

    def run(argv: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del argv
        captured.update(kwargs["env"])  # type: ignore[arg-type]
        return subprocess.CompletedProcess("supervisor", 0, '{"activated":true}\n', "")

    monkeypatch.setattr(environment_module.subprocess, "run", run)
    environment_module._activate_workflow_control(
        "supervisor",
        data_dir=tmp_path / "desktop-state",
        bundle=bundle,
        environment={
            "NXD_EVAL_SOURCE_TOKEN": "explicit-secret",
            "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": "caller=CALLER_TOKEN",
        },
    )

    assert "NXD_EVAL_SOURCE_TOKEN" not in captured
    assert captured["NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS"] == "caller=CALLER_TOKEN"
    assert "ambient-secret" not in captured.values()
    assert "explicit-secret" not in captured.values()
def test_workflow_activation_only_receives_allowlisted_and_explicit_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "activation.json"
    bundle.write_text('{}\n', encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-openai-key")
    monkeypatch.setenv("CUSTOM_SUPERVISOR_TOKEN", "ambient-custom-token")
    monkeypatch.setenv("WAREHOUSE_TOKEN", "ambient-warehouse-token")
    captured: dict[str, str] = {}

    def run(argv: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del argv
        captured.update(kwargs["env"])  # type: ignore[arg-type]
        return subprocess.CompletedProcess("supervisor", 0, '{"activated":true}\n', "")

    monkeypatch.setattr(environment_module.subprocess, "run", run)
    environment_module._activate_workflow_control(
        "supervisor",
        data_dir=tmp_path / "desktop-state",
        bundle=bundle,
        environment={"WAREHOUSE_TOKEN": "explicit-warehouse-token"},
    )

    assert captured["WAREHOUSE_TOKEN"] == "explicit-warehouse-token"
    assert "OPENAI_API_KEY" not in captured
    assert "CUSTOM_SUPERVISOR_TOKEN" not in captured


def test_workflow_activation_diagnostics_redact_source_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "activation.json"
    bundle.write_text('{}\n', encoding="utf-8")
    monkeypatch.setenv("NXD_EVAL_SOURCE_TOKEN", "ambient-secret")
    monkeypatch.setenv(
        "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS",
        "api-source=NXD_EVAL_SOURCE_TOKEN",
    )

    def run(argv: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del argv, kwargs
        return subprocess.CompletedProcess(
            "supervisor",
            7,
            "source=ambient-secret\n",
            "source=ambient-secret",
        )

    monkeypatch.setattr(environment_module.subprocess, "run", run)
    with pytest.raises(RunEnvironmentError) as excinfo:
        environment_module._activate_workflow_control(
            "supervisor",
            data_dir=tmp_path / "desktop-state",
            bundle=bundle,
            environment={"NXD_EVAL_SOURCE_TOKEN": "explicit-secret"},
        )

    detail = str(excinfo.value)
    assert "ambient-secret" not in detail
    assert "explicit-secret" not in detail
    assert "<redacted>" in detail


def test_workflow_activation_only_receives_allowlisted_and_explicit_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "activation.json"
    bundle.write_text('{}\n', encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-openai-key")
    monkeypatch.setenv("CUSTOM_SUPERVISOR_TOKEN", "ambient-custom-token")
    monkeypatch.setenv("WAREHOUSE_TOKEN", "ambient-warehouse-token")
    captured: dict[str, str] = {}

    def run(argv: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del argv
        captured.update(kwargs["env"])  # type: ignore[arg-type]
        return subprocess.CompletedProcess("supervisor", 0, '{"activated":true}\n', "")

    monkeypatch.setattr(environment_module.subprocess, "run", run)
    environment_module._activate_workflow_control(
        "supervisor",
        data_dir=tmp_path / "desktop-state",
        bundle=bundle,
        environment={"WAREHOUSE_TOKEN": "explicit-warehouse-token"},
    )

    assert captured["WAREHOUSE_TOKEN"] == "explicit-warehouse-token"
    assert "OPENAI_API_KEY" not in captured
    assert "CUSTOM_SUPERVISOR_TOKEN" not in captured


def test_workflow_activation_fails_closed_without_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "activation.json"
    bundle.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        environment_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "{}\n", ""),
    )

    with pytest.raises(RunEnvironmentError, match="did not confirm activation"):
        environment_module._activate_workflow_control(
            "/opt/nxd/supervisor",
            data_dir=tmp_path / "desktop-state",
            bundle=bundle,
            environment={},
        )
