"""Guard tests for the runner's live and replay CLI wiring."""

from __future__ import annotations

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
            "--knob-plan",
            str(tmp_path / "knobs.json"),
            "--report-json",
            str(report),
        ]
    )

    assert status == 0
    assert captured["live_command"] == ("fake-turn", "--flag", "value with spaces")
    assert captured["supervisor_command"] == supervisor
    assert callable(captured["session_factory"])
    assert captured["replay_recordings"] == {}
    assert captured["knob_plan"] == knob_plan


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


@pytest.mark.parametrize("tier", ["smoke", "core"])
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
