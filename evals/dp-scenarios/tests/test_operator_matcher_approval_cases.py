"""Fixture-backed matcher regressions from the live conversation review."""

from __future__ import annotations

import json
from pathlib import Path

from dp_scenarios.operator.matcher import MatcherBank
from dp_scenarios.scenario import load_scenario

ROOT = Path(__file__).parents[1]
CASE_FIXTURE = ROOT / "tests/fixtures/operator-matcher-approval-cases.json"


def test_recap_and_direct_decision_cases_resolve_to_the_declared_routes() -> None:
    fixture = json.loads(CASE_FIXTURE.read_text(encoding="utf-8"))
    assert fixture["schema"] == "operator-matcher-approval-cases-v1"

    scenarios = {}
    for case in fixture["cases"]:
        scenario_id = case["scenario_id"]
        scenario = scenarios.setdefault(
            scenario_id, load_scenario(ROOT / "scenarios" / scenario_id)
        )
        match = MatcherBank(scenario.persona, scenario.answer_sheet).reply_for(
            case["message"]
        )

        assert match.rule_id == case["expected_rule_id"], case["source"]
        assert match.decision_id == case["expected_decision_id"], case["source"]
