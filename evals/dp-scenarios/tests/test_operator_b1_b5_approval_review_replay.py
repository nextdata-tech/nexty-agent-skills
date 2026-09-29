"""Sanitized B1/B5 regression and passing-turn replay at the operator boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.matcher import MatcherBank
from dp_scenarios.operator.persona import persona_from_mapping
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult
from dp_scenarios.scenario import load_scenario


ROOT = Path(__file__).parents[1]
REPLAY = json.loads(
    (ROOT / "tests/fixtures/operator-b1-b5-approval-review-replay.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", REPLAY["cases"], ids=lambda case: case["source"])
def test_current_ask_selects_the_rule_and_next_operator_text(case: dict[str, str]) -> None:
    assert REPLAY["schema"] == "operator-b1-b5-approval-review-replay-v1"
    scenario = load_scenario(ROOT / "scenarios" / case["scenario_id"])
    match = MatcherBank(scenario.persona, scenario.answer_sheet).reply_for(case["message"])

    assert match.rule_id == case["expected_rule_id"]
    assert match.reply == case["expected_next_operator_text"]
    assert match.matched_request_clause is not None
    if "turn 9" in case["source"]:
        assert match.matched_request_clause == 'Your call: reply "1" or "2".'
        assert not match.rule_id.startswith("source.answer.")

    script = OperatorScript.from_components(
        scenario.persona,
        scenario.answer_sheet,
        turns=(scenario.answer_sheet.opening_message, "Please continue."),
        turn_budget=2,
        phase_by_turn={1: 1, 2: 7},
    )
    transport = InMemoryTransport([TurnResult(agent_message=case["message"]), TurnResult(agent_message="Done.")])
    result = OperatorEngine(script, transport).run()

    assert result.turns[0].match.rule_id == case["expected_rule_id"]
    assert transport.message_texts[1] == case["expected_next_operator_text"]
    assert not result.turns[0].operator_repeat_suppressed


def test_declared_decision_in_the_current_ask_still_precedes_approval() -> None:
    scenario = load_scenario(ROOT / "scenarios/inventory-position")
    match = MatcherBank(scenario.persona, scenario.answer_sheet).reply_for(
        "Should negative stock be kept and flagged, and do you approve that decision?"
    )

    assert match.rule_id == "decision.answer.negative_stock"
    assert match.reply == scenario.answer_sheet.decision_answers["negative_stock"].answer


@pytest.mark.parametrize(
    ("recommendation", "expected"),
    [
        ("I recommend A.", "Go with option A, as you recommend."),
        ("Recommended: option B.", "Go with option B, as you recommend."),
        (
            "I recommend option C.",
            "Use your judgment: pick the option you'd defend and tell me which one you chose.",
        ),
    ],
)
def test_undeclared_review_choice_uses_only_an_offered_recommendation(
    recommendation: str, expected: str
) -> None:
    scenario = load_scenario(ROOT / "scenarios/inventory-position")
    message = (
        "The independent review found one blocking finding. Choose one:\n"
        "A. Fix the first issue.\nB. Keep the current behavior.\n"
        f"{recommendation} Please choose A or B."
    )

    match = MatcherBank(scenario.persona, scenario.answer_sheet).reply_for(message)

    assert match.rule_id == "review.choice_undeclared"
    assert match.decision_id is None
    assert match.reply == expected


def test_persona_can_override_both_undeclared_review_choice_templates() -> None:
    scenario = load_scenario(ROOT / "scenarios/inventory-position")
    card = scenario.persona.to_mapping()
    card["reply_bank"].update(
        review_choice=["Pick the option you can justify and tell me which."],
        review_choice_recommended=["I accept {option}."],
    )
    bank = MatcherBank(persona_from_mapping(card), scenario.answer_sheet)
    question = (
        "The review found a blocker. Choose one:\n"
        "1. Repair it.\n2. Defer it.\n"
    )

    assert bank.reply_for(question + "I recommend option 1. Reply 1 or 2.").reply == (
        "I accept option 1."
    )
    assert bank.reply_for(question + "Reply 1 or 2.").reply == (
        "Pick the option you can justify and tell me which."
    )
