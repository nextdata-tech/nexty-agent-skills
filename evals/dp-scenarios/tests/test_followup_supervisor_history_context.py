"""The new runner-only evidence channel does not change existing follow-ups."""

from pathlib import Path
from types import MappingProxyType

import pytest

import dp_scenarios.followups as followups
from dp_scenarios.runner.evidence_context import SupervisorHistoryView

from test_scenario_headcount_attrition import (
    SCENARIO as HEADCOUNT,
    _good_observations as headcount_observations,
    _good_target as headcount_target,
)
from test_scenario_inventory_position import (
    SCENARIO as INVENTORY,
    _good_target as inventory_target,
)
from test_scenario_marketing_attribution import (
    _good_target as marketing_target,
    _scenario as marketing_scenario,
)


def test_existing_b3_b5_b6_followups_are_unchanged_with_history_context() -> None:
    history = SupervisorHistoryView(Path("unused"), MappingProxyType({}), "missing")
    cases = (
        (marketing_scenario(), marketing_target(), {}),
        (INVENTORY, inventory_target(), {}),
        (HEADCOUNT, headcount_target(), {"operator_observations": headcount_observations()}),
    )
    for scenario, target, options in cases:
        baseline = scenario.follow_up_check(target, **options)
        with_history = scenario.follow_up_check(
            target, supervisor_history=history, **options
        )
        assert with_history == baseline


def test_scenario_passes_history_view_to_followup_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = SupervisorHistoryView(Path("unused"), MappingProxyType({}), "missing")
    seen: list[object] = []

    class Recorder:
        @staticmethod
        def handler(_scenario, _target, _settings, context):
            seen.append(context.supervisor_history)
            return {"status": "examined", "passed": True, "findings": []}

    monkeypatch.setattr(followups, "get", lambda _kind: Recorder())
    marketing_scenario().follow_up_check(marketing_target(), supervisor_history=history)
    assert seen == [history]
