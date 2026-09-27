"""Replay of live B2 run 16's agent messages against the finance-close script.

Run 16 ended with no published build for two operator reasons. Turns 2-4
re-sent the already-delivered weekend-FX decision answer to questions about
other things (the sign-off rubric, amount parsing) that only mentioned
"weekend" and "rate". And after the operator handed an unencoded decision
back ("I don't know, you tell me.") and the agent returned with its own
proposed rule, the micromanager persona only ever asked "What exactly am I
approving?", so the ask-back stance's second half -- go with the agent's
recommendation -- never happened.
"""

from __future__ import annotations

import json
from pathlib import Path

from dp_scenarios.operator.answer_sheet import load_answer_sheet
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.events import load_event_cards
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult

ROOT = Path(__file__).parents[1]
FIXTURES = json.loads((ROOT / "tests/fixtures/operator-b2-run16-replay.json").read_text())
MESSAGES = FIXTURES["b2_run16_agent_messages"]
FINANCE_CLOSE = load_answer_sheet(ROOT / "scenarios/finance-close/answer-sheet.yaml")
PERSONA = load_persona(ROOT / "scenarios/_personas/micromanager.yaml")
ACCEPTANCE = "Yes, go with your recommendation."


def _replay() -> tuple[object, InMemoryTransport]:
    turns = FINANCE_CLOSE.turns
    script = OperatorScript.from_components(
        PERSONA,
        FINANCE_CLOSE,
        events=load_event_cards(ROOT / "scenarios/finance-close/events.yaml"),
        turns=turns,
        turn_budget=len(turns),
        phase_by_turn={turn: min(turn, 7) for turn in range(1, len(turns) + 1)},
    )
    transport = InMemoryTransport([TurnResult(agent_message=text) for text in MESSAGES])
    return OperatorEngine(script, transport).run(), transport


def test_the_weekend_fx_answer_is_not_resent_to_different_questions() -> None:
    _, transport = _replay()
    answer = FINANCE_CLOSE.decision_answers["weekend_fx"].answer

    # Before the scripted decision event (turn 4), the declared answer goes
    # out once, for turn 1's actual missing-FX question.
    assert sum(answer in text for text in transport.message_texts[1:4]) == 1


def test_the_agents_own_proposal_after_a_hand_back_is_accepted() -> None:
    result, transport = _replay()

    # Turn 12's agent reply asks for the unencoded blank-amount decision; the
    # operator hands it back at turn 13. Turn 13's agent reply proposes a rule
    # and asks "Do you approve this specific rule?".
    assert transport.message_texts[12] == "I don't know, you tell me."
    assert result.turns[12].match.rule_id == "stance.ask_back.accept_recommendation"
    assert transport.message_texts[13] == ACCEPTANCE
    assert result.ledger_rows[13]["action_kind"] != "spec_approved"
