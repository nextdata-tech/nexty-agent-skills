"""Guard tests for the runner's live and replay CLI wiring."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import dp_scenarios.runner.cli as cli
from dp_scenarios.knobs import SupervisorKnobs, WorkflowSwitchPlan


def test_live_cli_wires_session_and_supervisor_commands(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class StubRunner:
        def __init__(self, scenarios, **kwargs):
            captured["scenarios"] = scenarios
            captured.update(kwargs)

        def run(self):
            return SimpleNamespace(verdict="clean")

    supervisor = tmp_path / "supervisor"
    report = tmp_path / "report.json"
    monkeypatch.setattr(
        cli, "load_scenarios", lambda _root: [SimpleNamespace(id="scenario-1", tier="smoke")]
    )
    monkeypatch.setattr(
        cli,
        "load_claims",
        lambda _path: SimpleNamespace(baseline=SimpleNamespace(approves_claims_hash="claims-1")),
    )
    monkeypatch.setattr(cli, "_read_json", lambda _path: {})
    monkeypatch.setattr(cli, "_canary_from_mapping", lambda *args, **kwargs: object())
    monkeypatch.setattr(cli, "write_report", lambda _result, **kwargs: None)
    monkeypatch.setattr(cli, "TierRunner", StubRunner)
    knob_plan = {("scenario-1", 1): SupervisorKnobs.off()}
    monkeypatch.setattr(cli, "load_knob_plan", lambda _path: knob_plan)

    status = cli.main(
        [
            "--mode",
            "live",
            "--scenario-root",
            str(tmp_path / "scenarios"),
            "--tier",
            "smoke",
            "--canary-dir",
            str(tmp_path / "canary"),
            "--skills-root",
            str(tmp_path / "skills"),
            "--canary-replay",
            str(tmp_path / "canary-replay.json"),
            "--session-command",
            "fake-turn --flag 'value with spaces'",
            "--supervisor",
            str(supervisor),
            "--skill-pack-version",
            "skills-1",
            "--supervisor-version",
            "supervisor-1",
            "--runtime-wheel-version",
            "wheel-1",
            "--mock-api-version",
            "mock-1",
            "--canary-claims-hash",
            "claims-1",
            "--jobs",
            "2",
            "--knob-plan",
            str(tmp_path / "knobs.json"),
            "--report-json",
            str(report),
        ]
    )

    assert status == 0
    assert captured["live_command"] == ("fake-turn", "--flag", "value with spaces")
    assert captured["supervisor_command"] == supervisor
    assert captured["workflow_activation_bundle"] == cli.DEFAULT_WORKFLOW_ACTIVATION_BUNDLE
    assert callable(captured["session_factory"])
    assert captured["replay_recordings"] == {}
    assert captured["knob_plan"] == knob_plan
    assert captured["max_workers"] == 2


def test_cli_rejects_workflow_switch_without_endpoint_callbacks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        cli,
        "load_knob_plan",
        lambda _path: {
            ("scenario-1", 1): SupervisorKnobs(
                workflow_switch=WorkflowSwitchPlan("old", "new")
            )
        },
    )

    with pytest.raises(cli.TierError, match="cannot execute workflow switches"):
        cli._load_cli_knob_plan(tmp_path / "knobs.json")


def _replay_argv(tmp_path: Path, tier: str, mode: str) -> list[str]:
    return [
        "--mode", mode,
        "--scenario-root", str(tmp_path / "scenarios"),
        "--tier", tier,
        "--canary-dir", str(tmp_path / "canary"),
        "--skills-root", str(tmp_path / "skills"),
        "--skill-pack-version", "skills-1",
        "--supervisor-version", "supervisor-1",
        "--runtime-wheel-version", "wheel-1",
        "--mock-api-version", "mock-1",
        "--canary-claims-hash", "claims-1",
        "--report-json", str(tmp_path / "report.json"),
    ]


def test_a_live_tier_run_in_replay_mode_is_refused_before_anything_loads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Replaying a live-tier scenario would grade the recording, not an agent.

    The refusal has to happen before ``load_scenarios``: a run that got as far
    as selecting packages and then produced a report would be
    indistinguishable from a real one in the report file, which is worse than
    a run that fails loudly.
    """

    def explode(_root):  # pragma: no cover - asserted not to run
        raise AssertionError("scenarios were loaded despite the refusal")

    monkeypatch.setattr(cli, "load_scenarios", explode)
    with pytest.raises(cli.TierError, match="requires --mode live"):
        cli.main(_replay_argv(tmp_path, "live", "replay"))


@pytest.mark.parametrize("tier", ["smoke", "core", "full"])
def test_a_non_live_tier_is_not_refused_in_replay_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tier: str
) -> None:
    """The refusal is scoped to the live tier, not to replay mode generally.

    Without this, widening the predicate to every tier -- which would break
    every existing replay run -- still satisfies the test above.
    """

    seen: list[Path] = []

    def record(root):
        seen.append(root)
        raise cli.TierError("stopped after the tier check")

    monkeypatch.setattr(cli, "load_scenarios", record)
    with pytest.raises(cli.TierError, match="stopped after the tier check"):
        cli.main(_replay_argv(tmp_path, tier, "replay"))
    assert seen, f"tier {tier!r} was refused before loading"


# ---------------------------------------------------------------------------
# The driver flags, mirrored from the local live entrypoint
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_network_for_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    import aiohttp

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("test attempted a real network call")

    monkeypatch.setattr(aiohttp, "ClientSession", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _cli_pins():
    from dp_scenarios.runner.environment import PinnedVersions

    return PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1")


def test_runner_cli_mirrors_the_driver_flags_and_defaults_to_scripted() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "--scenario-root", "x", "--tier", "smoke", "--canary-dir", "c",
            "--skills-root", "s", "--skill-pack-version", "1", "--supervisor-version", "2",
            "--runtime-wheel-version", "3", "--mock-api-version", "4", "--canary-claims-hash", "5",
            "--report-json", "r.json",
        ]
    )

    assert args.driver_model is None
    assert args.driver_temperature == 1.0
    assert args.driver_timeout == 60.0
    assert args.driver_max_tokens == 400
    assert args.jobs == 1

    pins, factory = cli._driver_configuration(args, _cli_pins())
    assert factory is None
    assert pins.driver_model_id == "not-applicable"


@pytest.mark.parametrize("jobs", [0, -1])
def test_runner_cli_rejects_non_positive_jobs(
    tmp_path: Path, jobs: int
) -> None:
    with pytest.raises(cli.TierError, match="--jobs must be a positive integer"):
        cli.main(_replay_argv(tmp_path, "smoke", "replay") + ["--jobs", str(jobs)])


def test_runner_cli_driver_requires_the_key_and_pins_the_prompt_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dp_scenarios.operator.openai_driver import DriverConfigError, driver_prompt_hash

    args = SimpleNamespace(
        mode="live",
        driver_model="gpt-x",
        driver_temperature=0.3,
        driver_timeout=30.0,
        driver_max_tokens=900,
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(DriverConfigError, match="OPENAI_API_KEY"):
        cli._driver_configuration(args, _cli_pins())

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    pins, factory = cli._driver_configuration(args, _cli_pins())

    assert pins.driver_model_id == "gpt-x"
    # The completion cap is pinned alongside the prompt hash: it decides
    # whether a turn produces text at all, so two runs differing by it are
    # two different operators and must not pair.
    assert dict(pins.driver_sampling_params) == {
        "temperature": 0.3,
        "max_tokens": 900,  # the flag value, not the default -- proves it flows through
        "prompt_hash": driver_prompt_hash(),
    }
    operator = factory(object(), object(), 1)
    assert operator.model_id == "gpt-x"
    assert operator.temperature == 0.3
    assert operator.provider.max_tokens == 900
    assert "sk-test" not in repr(operator)


def test_runner_cli_refuses_a_driver_in_replay_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replaying a recording re-authors nothing; a driver would only spend tokens."""

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    args = SimpleNamespace(
        mode="replay",
        driver_model="gpt-x",
        driver_temperature=0.3,
        driver_timeout=30.0,
        driver_max_tokens=400,
    )

    with pytest.raises(cli.TierError, match="--driver-model requires --mode live"):
        cli._driver_configuration(args, _cli_pins())


def test_live_runner_defaults_to_the_packaged_workflow_activation_bundle() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "--scenario-root", "scenarios", "--tier", "smoke",
            "--canary-dir", "canary", "--skills-root", "skills",
            "--skill-pack-version", "1", "--supervisor-version", "2",
            "--runtime-wheel-version", "3", "--mock-api-version", "4",
            "--canary-claims-hash", "5", "--report-json", "report.json",
        ]
    )

    assert args.workflow_activation_bundle.is_file()
    assert json.loads(args.workflow_activation_bundle.read_text(encoding="utf-8"))[
        "schema"
    ] == "nxd-workflow-activation-v1"
