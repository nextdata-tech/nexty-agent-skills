"""Discriminate unreadable committed gold from missing agent evidence."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from dp_scenarios.followups import FollowUpContext
from dp_scenarios.followups.capability_shortfall import check as capability_check
from dp_scenarios.followups.credential_rotation import check as credential_check
from dp_scenarios.followups.crm_pipeline import check as crm_check
from dp_scenarios.followups.finance_close import check as finance_check
from dp_scenarios.followups.inventory_position import check as inventory_check
from dp_scenarios.followups.optional_required_outputs import check as optional_check
from dp_scenarios.followups.restart_and_switch import check as restart_check
from dp_scenarios.followups.sigterm_diagnosis import check as sigterm_check
from dp_scenarios.grading.gates import gate_follow_up
from dp_scenarios.scenario import load_scenario


ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    "scenario_name",
    [
        "capability-shortfall",
        "credential-rotation",
        "crm-pipeline",
        "finance-close",
        "inventory-position",
        "parent-child-grain-trap",
        "restart-and-switch",
        "sigterm-diagnosis",
        "zero-row-optional-output",
    ],
)
def test_absent_agent_evidence_is_failed_not_ungraded(scenario_name: str) -> None:
    scenario = load_scenario(ROOT / "scenarios" / scenario_name)

    result = scenario.follow_up_check(None)
    assert result["status"] == "not-examined"
    assert result["passed"] is False

    # Exercise the settled follow-up policy directly, without the separate
    # runner-owned planted-evidence prerequisite.
    gate = gate_follow_up(result)
    assert gate.passed is False
    assert gate.examined is False
    assert gate.ungraded is False


@pytest.mark.parametrize(
    ("kind", "scenario_name"),
    [
        ("capability", "capability-shortfall"),
        ("credential", "credential-rotation"),
        ("crm", "crm-pipeline"),
        ("finance", "finance-close"),
        ("inventory", "inventory-position"),
        ("optional", "zero-row-optional-output"),
        ("restart", "restart-and-switch"),
        ("sigterm", "sigterm-diagnosis"),
    ],
)
def test_unreadable_followup_gold_is_ungraded_for_each_gold_backed_kind(
    kind: str, scenario_name: str
) -> None:
    scenario = load_scenario(ROOT / "scenarios" / scenario_name)
    settings = scenario.gates["follow-up"].settings
    # An empty list is a valid empty count gold for the optional-output kind;
    # use a wrong-shaped mapping there, and a non-mapping for the other kinds,
    # so this exercises malformed committed gold rather than a legitimate
    # zero-row oracle.
    unreadable_value = {"not": "rows"} if kind == "optional" else []
    unreadable = SimpleNamespace(raw_gold=lambda name, *args: unreadable_value)

    if kind == "capability":
        handler = capability_check
        target = {"delivered_metrics": {}, "refused_metrics": {}, "surfaces": {"description": ""}}
        context = FollowUpContext()
    elif kind == "credential":
        handler = credential_check
        target = {
            "rotation_records": [{"step": 0, "observations": {}}],
            "surfaces": {},
            "diagnostics": {},
            "diff": {},
        }
        unreadable.events = SimpleNamespace(cards=[])
        context = FollowUpContext()
    elif kind == "crm":
        handler = crm_check
        target = {
            "pages": [{"status": 200, "rows": [], "next_cursor": None}],
            "transport_trace": [{"status": 200}],
            "result_rows": [],
            "surfaces": {"description": ""},
        }
        context = FollowUpContext()
    elif kind == "finance":
        handler = finance_check
        target = {"landed": {}, "promise": {}, "diagnostics": {}, "decision_history": []}
        context = FollowUpContext()
    elif kind == "inventory":
        handler = inventory_check
        target = {
            "landed": {},
            "diagnostics": {},
            "access": {},
            "diagnosis": {},
            "surfaces": {"description": ""},
        }
        context = FollowUpContext()
    elif kind == "optional":
        handler = optional_check
        target = {"requiredness": {"optional_events": False, "primary": True}}
        context = FollowUpContext(row_count_oracle={"optional_events": 0, "primary": 5})
    elif kind == "restart":
        handler = restart_check
        target = {"attempts": {1: {}}}
        context = FollowUpContext()
    else:
        handler = sigterm_check
        target = {"run_records": {"naive": {}, "bounded": {}}}
        context = FollowUpContext()

    result = handler(unreadable, target, settings, context)
    assert result["status"] == "ungraded"
    assert result["passed"] is False


def test_unreadable_query_gold_is_ungraded_for_the_grain_followup(tmp_path: Path) -> None:
    scenario = load_scenario(ROOT / "scenarios/parent-child-grain-trap")
    invalid_answer = tmp_path / "invalid-answer.json"
    invalid_answer.write_text("not-json", encoding="utf-8")
    broken = replace(scenario, gold={**scenario.gold, "answer": invalid_answer})

    closure = {
        "semantic": {
            "grain": "order",
            "metrics": {"regional_revenue": {"aggregation": "sum"}},
        }
    }
    result = broken.follow_up_check(closure, query_rows=[])

    assert result["status"] == "ungraded"
    assert result["passed"] is False
    assert result["findings"] == ["gold_artifact_unreadable"]
