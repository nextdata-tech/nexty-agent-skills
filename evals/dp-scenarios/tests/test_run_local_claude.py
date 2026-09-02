"""Contract tests for the local Claude Code entrypoint helpers."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from dp_scenarios.runner.tier import TierError
from dp_scenarios.grading.statistics import RepeatabilityTier
from dp_scenarios.scenario import RepeatabilitySpec


SCRIPT = Path(__file__).parents[1] / "scripts/run_local_claude.py"


@dataclass(frozen=True)
class _ScenarioStub:
    id: str
    repeatability: RepeatabilitySpec


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("dp_scenarios_run_local_claude", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_runner_selects_declared_scenarios_and_rejects_unknown_ids() -> None:
    module = _load_runner_module()
    scenarios = (SimpleNamespace(id="first"), SimpleNamespace(id="second"))

    assert module._select_scenarios(scenarios, ["second"]) == (scenarios[1],)
    with pytest.raises(TierError, match="unknown scenario id"):
        module._select_scenarios(scenarios, ["missing"])


def test_local_runner_marks_single_epoch_runs_as_demonstrated_once() -> None:
    module = _load_runner_module()
    scenario = _ScenarioStub(
        id="scenario",
        repeatability=RepeatabilitySpec(
            RepeatabilityTier.DETERMINISTIC,
            5,
            "wilson_lower_bound",
            ("build",),
            0.9,
            0.95,
        ),
    )

    configured = module._configure_scenarios((scenario,), [], 1)

    assert configured[0].repeatability.epochs == 1
    assert configured[0].repeatability.tier is RepeatabilityTier.DEMONSTRATED_ONCE


def test_local_runner_leaves_timeout_budget_for_the_adapter() -> None:
    module = _load_runner_module()

    assert module._adapter_timeout(10.0) == pytest.approx(9.0)
    assert module._adapter_timeout(0.1) < 0.1


def test_local_runner_host_home_is_explicit_and_bash_requires_a_second_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_runner_module()
    monkeypatch.setattr(module.Path, "home", classmethod(lambda _cls: Path("/host-home")))

    sandbox = {"HOME": "/sandbox-home", "USERPROFILE": "/sandbox-home"}
    assert module._agent_environment(sandbox, allow_host_home=False) == sandbox
    assert module._agent_environment(sandbox, allow_host_home=True)["HOME"] == "/host-home"

    args = module.build_parser().parse_args(["--allow-host-home", "--allow-host-home-bash"])
    assert args.allow_host_home is True
    assert args.allow_host_home_bash is True

    with pytest.raises(TierError, match="requires --allow-host-home"):
        module.main(["--allow-host-home-bash"])
