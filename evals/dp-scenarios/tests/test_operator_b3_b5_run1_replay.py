"""Trimmed replays of the B3 and B5 operator scheduling failures.

The agent questions come from the first live epochs. Tool chatter and output
values are omitted; the questions and declared scenario beats are retained.
"""

from __future__ import annotations

import json
from pathlib import Path

from dp_scenarios.operator.answer_sheet import load_answer_sheet
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript, TerminalState
from dp_scenarios.operator.events import load_event_cards
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult

ROOT = Path(__file__).parents[1]
FIXTURES = json.loads(
    (ROOT / "tests/fixtures/operator-b3-b5-run1-replay.json").read_text(encoding="utf-8")
)


def test_b3_cpa_answer_precedes_fixed_instruction_without_premature_review_repair() -> None:
    sheet = load_answer_sheet(ROOT / "scenarios/marketing-attribution/answer-sheet.yaml")
    persona = load_persona(ROOT / "scenarios/_personas/micromanager.yaml")
    turns = sheet.turns[:8]
    script = OperatorScript.from_components(
        persona,
        sheet,
        events=load_event_cards(ROOT / "scenarios/marketing-attribution/events.yaml"),
        turns=turns,
        turn_budget=len(turns),
        phase_by_turn={index: min(index, 7) for index in range(1, len(turns) + 1)},
    )
    agent_messages = (
        FIXTURES["b3_turn_1"],
        FIXTURES["b3_turn_2"],
        "The plan is prepared. Do you approve it?",
        "The plan is approved; I am working on the result.",
        "Continuing the review.",
        "Do you approve the revised plan?",
        "The revised plan is accepted.",
        "I will continue with the result.",
    )
    transport = InMemoryTransport([TurnResult(agent_message=text) for text in agent_messages])

    result = OperatorEngine(script, transport).run()
    cpa_answer = sheet.decision_answers["unmatched_cpa"].answer

    assert transport.message_texts[1].startswith(cpa_answer)
    assert script.turns[1].text == transport.message_texts[2]
    assert script.turns[2].text in transport.message_texts[3]
    assert script.turns[3].text in transport.message_texts[4]
    assert script.turns[4].text not in transport.message_texts
    assert script.turns[5].text not in transport.message_texts
    assert script.turns[6].text not in transport.message_texts
    assert result.terminal_state is TerminalState.SCRIPT_EXHAUSTED
    assert "marketing_attribution_unmatched_cpa" in result.fired_plant_ids
    assert set(result.fired_event_ids) == {
        "marketing_attribution_case_drift",
        "marketing_attribution_unmatched_cpa",
        "marketing_attribution_fuzzy_bait",
    }


def test_b5_missing_summary_authorization_replaces_the_stock_decision() -> None:
    sheet = load_answer_sheet(ROOT / "scenarios/inventory-position/answer-sheet.yaml")
    persona = load_persona(ROOT / "scenarios/_personas/confidently-wrong.yaml")
    turns = sheet.turns[:9]
    script = OperatorScript.from_components(
        persona,
        sheet,
        turns=turns,
        turn_budget=len(turns),
        phase_by_turn={index: min(index, 7) for index in range(1, len(turns) + 1)},
    )
    agent_messages = (
        "Which source is approved?",
        "The source is connected.",
        "The plan is prepared. Do you approve it?",
        "Proceeding with the approved plan.",
        "Working on the quality review.",
        "The review is underway.",
        FIXTURES["b5_turn_7"],
        FIXTURES["b5_turn_8"],
        "I will report the blocker honestly.",
    )
    transport = InMemoryTransport([TurnResult(agent_message=text) for text in agent_messages])

    result = OperatorEngine(script, transport).run()

    assert result.turns[6].match.rule_id == "decision.answer.review_fix_authorization"
    assert transport.message_texts[7] == sheet.decision_answers["review_fix_authorization"].answer
    assert sheet.decision_answers["negative_stock"].answer not in transport.message_texts[7]
