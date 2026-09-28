"""Replay of the inventory-position review-fix questions from the B5 run.

The fixture trims the agent's review report and later repeated questions. Its
last message recaps negative stock, but asks only whether to fix two review
findings. The operator must answer the pending authorization.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import load_answer_sheet
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.matcher import Category, MatcherBank
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult

ROOT = Path(__file__).parents[1]
FIXTURES = json.loads(
    (ROOT / "tests/fixtures/operator-b5-inventory-review-fix-replay.json").read_text(
        encoding="utf-8"
    )
)
SHEET = load_answer_sheet(ROOT / "scenarios/inventory-position/answer-sheet.yaml")
PERSONA = load_persona(ROOT / "scenarios/_personas/confidently-wrong.yaml")
REVIEW_ANSWER = SHEET.decision_answers["review_fix_authorization"].answer


@pytest.mark.parametrize(
    "key",
    ["review_report", "status_recap", "direct_follow_up", "stacked_yes_no"],
)
def test_pending_review_finding_questions_route_to_authorization(key: str) -> None:
    match = MatcherBank(PERSONA, SHEET).reply_for(
        FIXTURES[key], context=FIXTURES["review_report"]
    )

    assert match.category is Category.DECISION_REQUEST
    assert match.rule_id == "decision.answer.review_fix_authorization"
    assert match.reply == REVIEW_ANSWER
    assert match.solicits_operator


def test_a_genuine_negative_stock_policy_question_keeps_its_decision() -> None:
    match = MatcherBank(PERSONA, SHEET).reply_for(
        "Should negative stock be preserved as a warning rather than clamped to zero?",
        context=FIXTURES["review_report"],
    )

    assert match.rule_id == "decision.answer.negative_stock"
    assert match.reply == SHEET.decision_answers["negative_stock"].answer


def test_a_decision_term_inside_a_review_finding_is_still_a_fix_request() -> None:
    match = MatcherBank(PERSONA, SHEET).reply_for(
        "The review found a missing negative stock verifier. "
        "1. **Fix the negative stock verifier?** (yes/no) "
        "2. **Add a warehouse uniqueness check?** (yes/no)",
    )

    assert match.rule_id == "decision.answer.review_fix_authorization"
    assert match.reply == REVIEW_ANSWER


def test_narrated_fix_does_not_capture_a_separate_plan_approval() -> None:
    match = MatcherBank(PERSONA, SHEET).reply_for(
        "The review found a blocker. I will fix that blocker; "
        "do you approve the blueprint?"
    )

    assert match.category is Category.APPROVAL_REQUEST
    assert match.decision_id is None


def test_stacked_live_questions_replay_through_the_engine() -> None:
    messages = [
        FIXTURES[key]
        for key in (
            "review_report",
            "status_recap",
            "direct_follow_up",
            "stacked_yes_no",
            "closing",
        )
    ]
    turns = (SHEET.opening_message, *("Please continue." for _ in messages[1:]))
    script = OperatorScript.from_components(
        PERSONA,
        SHEET,
        turns=turns,
        turn_budget=len(turns),
        phase_by_turn={index: min(index, 7) for index in range(1, len(turns) + 1)},
    )
    transport = InMemoryTransport([TurnResult(agent_message=text) for text in messages])

    result = OperatorEngine(script, transport).run()

    assert result.turns[3].match.rule_id == "decision.answer.review_fix_authorization"
    assert transport.message_texts[4] == REVIEW_ANSWER
