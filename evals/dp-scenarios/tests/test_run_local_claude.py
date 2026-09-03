"""Contract tests for the local Claude Code entrypoint helpers."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from dp_scenarios.runner.tier import TierError
from dp_scenarios.grading.statistics import RepeatabilityTier
from dp_scenarios.scenario import RepeatabilitySpec, load_scenarios


SCENARIO_ROOT = Path(__file__).resolve().parents[1] / "scenarios"
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


def test_local_runner_host_home_flag_and_bash_require_a_second_opt_in() -> None:
    module = _load_runner_module()

    args = module.build_parser().parse_args(["--allow-host-home", "--allow-host-home-bash"])
    assert args.allow_host_home is True
    assert args.allow_host_home_bash is True

    with pytest.raises(TierError, match="requires --allow-host-home"):
        module.main(["--allow-host-home-bash"])


def test_the_live_entrypoint_defaults_to_the_smoke_tier_not_every_package() -> None:
    """Omitting --scenario must not drive the core tier through a live session.

    This entrypoint spends model tokens against an authenticated Claude Code
    session. Before the tier boundary existed, "default: all" meant the two
    smoke packages; adding core packages to the same root silently made it
    mean those too -- including one that needs a Docker Postgres and one whose
    evidence a live run cannot produce. The runner CLI's boundary did not
    cover this second loader call site.
    """

    module = _load_runner_module()
    args = module.build_parser().parse_args([])
    assert args.tier == "smoke"
    assert args.scenario == []

    scenarios = load_scenarios(SCENARIO_ROOT)
    in_scope = module._scenarios_in_scope(scenarios, args.scenario, args.tier)
    assert {scenario.id for scenario in in_scope} == {
        scenario.id for scenario in scenarios if scenario.tier == "smoke"
    }
    assert all(scenario.tier == "smoke" for scenario in in_scope)
    assert len(in_scope) < len(scenarios), "the boundary excluded nothing"


def test_the_live_entrypoint_still_lets_an_explicit_id_cross_the_tier() -> None:
    """Naming a core scenario is the deliberate way to run one live."""

    module = _load_runner_module()
    args = module.build_parser().parse_args(["--scenario", "credential-rotation"])
    assert args.scenario == ["credential-rotation"]

    scenarios = load_scenarios(SCENARIO_ROOT)
    in_scope = module._scenarios_in_scope(scenarios, args.scenario, args.tier)
    assert {scenario.id for scenario in in_scope} == {scenario.id for scenario in scenarios}
