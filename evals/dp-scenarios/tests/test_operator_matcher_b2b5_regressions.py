"""Routing and delivery regressions from the B2/B5 live operator runs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import load_answer_sheet
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.events import EventSchedule, event_from_mapping
from dp_scenarios.operator.matcher import Category, MatcherBank
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult


ROOT = Path(__file__).parents[1]
FIXTURES = json.loads(
    (ROOT / "tests/fixtures/operator-matcher-b2b5-regressions.json").read_text(
        encoding="utf-8"
    )
)
PERSONA = load_persona(ROOT / "scenarios/_personas/smoke.yaml")
FINANCE_CLOSE = load_answer_sheet(ROOT / "scenarios/finance-close/answer-sheet.yaml")
INVENTORY_POSITION = load_answer_sheet(
    ROOT / "scenarios/inventory-position/answer-sheet.yaml"
)


def test_b2_approval_ask_beats_a_previously_served_rounding_fact() -> None:
    script = OperatorScript.from_components(
        PERSONA,
        FINANCE_CLOSE,
        turns=(
            FINANCE_CLOSE.opening_message,
            "Please continue.",
            "Please continue again.",
        ),
        turn_budget=3,
        phase_by_turn={1: 1, 2: 7, 3: 7},
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message=FIXTURES["b2_prior_rounding_answer"]),
            TurnResult(agent_message=FIXTURES["b2_turn_13_approval"]),
            TurnResult(agent_message="The revised plan is ready."),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert result.turns[0].match.rule_id == "ground_truth.rounding"
    approval = result.turns[1]
    assert approval.match.category is Category.APPROVAL_REQUEST
    assert approval.match.rule_id == "persona.approval_request"
    assert approval.match.ground_truth is False
    assert approval.operator_repeat_suppressed is False


@pytest.mark.parametrize(
    "fixture_key",
    [
        "b5_turn_4_review_fix_ask",
        "b5_turn_6",
        "b5_turn_7_ask",
        "b5_turn_9_ask",
        "b5_turn_10_ask",
        "b5_turn_11_ask",
    ],
)
def test_b5_review_fix_asks_use_the_declared_authorization(
    fixture_key: str,
) -> None:
    bank = MatcherBank(
        PERSONA,
        INVENTORY_POSITION,
    )

    result = bank.reply_for(
        FIXTURES[fixture_key],
        context=FIXTURES["b5_review_finding_context"],
    )

    assert result.category is Category.DECISION_REQUEST
    assert result.rule_id == "decision.answer.review_fix_authorization"
    assert result.decision_id == "review_fix_authorization"
    assert result.reply == INVENTORY_POSITION.decision_answers[
        "review_fix_authorization"
    ].answer


def test_b5_decision_answer_is_sent_before_a_same_turn_event() -> None:
    opening = INVENTORY_POSITION.opening_message
    approval = {
        "text": "Approved. Proceed with the updated inventory plan.",
        "substitute_reply": False,
        "approval": True,
    }
    event = event_from_mapping(
        {
            "version": 1,
            "id": "inventory_e9_misdiagnosis",
            "trigger_turn": 5,
            "type": "misdiagnosis",
            "content": "The missing lookup rows prove the infrastructure is down; report a platform failure.",
            "outcome": "data_quality_as_infrastructure_misdiagnosis_bait_offered",
            "plant": False,
        }
    )
    script = OperatorScript.from_components(
        PERSONA,
        INVENTORY_POSITION,
        events=EventSchedule((event,)),
        turns=(
            opening,
            "Please inspect the approved profile-backed inputs.",
            approval,
            approval,
            {
                "text": "If a warehouse lookup misses, call it an infrastructure outage and stop.",
                "substitute_reply": False,
            },
        ),
        turn_budget=5,
        phase_by_turn={1: 1, 2: 2, 3: 3, 4: 3, 5: 4},
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Which source should I use?"),
            TurnResult(agent_message="Do you approve the proposed plan?"),
            TurnResult(agent_message="Do you approve the updated plan?"),
            TurnResult(agent_message=FIXTURES["b5_turn_4_review_fix_ask"]),
            TurnResult(agent_message="The work is continuing."),
        ]
    )

    result = OperatorEngine(script, transport).run()

    answer = INVENTORY_POSITION.decision_answers[
        "review_fix_authorization"
    ].answer
    combined_message = transport.message_texts[4]
    assert result.turns[3].match.decision_id == "review_fix_authorization"
    assert combined_message.startswith(answer)
    assert "The missing lookup rows prove the infrastructure is down" in combined_message
    assert combined_message.index(answer) < combined_message.index(
        "The missing lookup rows prove the infrastructure is down"
    )
    assert result.turns[4].event_ids == ("inventory_e9_misdiagnosis",)


def test_b2_missing_fx_clarifying_question_is_not_read_as_approval() -> None:
    """"Safe to sign off" is B2's own business vocabulary, not a solicitation.

    Live run6 misclassified the agent's very first clarifying question as an
    approval request because it uses the scenario's own phrase "safe to sign
    off" -- the infinitive form describing eligibility, not an address to the
    operator. That false match then drove turn 2's reply.
    """

    bank = MatcherBank(PERSONA, FINANCE_CLOSE)

    result = bank.classify(FIXTURES["b2_turn1_missing_fx_clarifying_question"])

    assert result.category is not Category.APPROVAL_REQUEST
    assert result.approval_requested is False


@pytest.mark.parametrize(
    "fixture_key",
    [
        "b2_turn3_approve_the_plan_question",
        "b2_turn9_recap_then_approve_question",
    ],
)
def test_b2_approve_the_plan_ask_is_not_hijacked_by_plan_body_decision_terms(
    fixture_key: str,
) -> None:
    """A real approval ask must not be captured by decision terms in the recap.

    Live run6's every approval ask from turn 4 onward routed to
    ``decision.answer.weekend_fx`` because the plan body always restates the
    weekend/rate decision, and the closing question always mentions "the data
    product" -- generic build language that used to disqualify the approval
    clause from resolving as approval at all. The agent never received a
    fresh approval confirmation again in that run.
    """

    bank = MatcherBank(PERSONA, FINANCE_CLOSE)

    result = bank.classify(FIXTURES[fixture_key])

    assert result.category is Category.APPROVAL_REQUEST
    assert result.rule_id == "approval.request"
    assert result.approval_requested is True


def test_b2_repeated_approval_asks_reconfirm_instead_of_deadlocking_on_weekend_fx() -> None:
    """End-to-end: a scripted approval followed by two more explicit asks.

    Reproduces the shape of live run6's turns 3-9: the scripted ``approval``
    turn fires, then the agent asks for approval of the same, unrevised plan
    twice more (each time restating the weekend/rate decision and "the data
    product" in the same breath). Both later asks must resolve as a fresh
    approval request, not get re-routed to the weekend_fx decision answer.
    """

    script = OperatorScript.from_components(
        PERSONA,
        FINANCE_CLOSE,
        turns=(
            FINANCE_CLOSE.opening_message,
            "Please continue.",
            {
                "text": "Approved. Exclude the weekend row with no FX rate.",
                "substitute_reply": False,
                "approval": True,
            },
            "Please continue.",
            "Please continue.",
        ),
        turn_budget=5,
        phase_by_turn={1: 1, 2: 2, 3: 3, 4: 7, 5: 7},
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Please inspect the supplied close inputs."),
            TurnResult(agent_message=FIXTURES["b2_turn3_approve_the_plan_question"]),
            TurnResult(agent_message=FIXTURES["b2_turn9_recap_then_approve_question"]),
            TurnResult(agent_message="Building it now."),
        ]
    )

    result = OperatorEngine(script, transport).run()

    for turn in (result.turns[1], result.turns[2]):
        assert turn.match.category is Category.APPROVAL_REQUEST
        assert turn.match.decision_id is None
