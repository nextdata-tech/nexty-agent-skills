"""Trimmed B7 run-2 asks: the last addressed choice owns the next reply."""

from __future__ import annotations

import json
from pathlib import Path

from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.matcher import Category, MatcherBank
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult
from dp_scenarios.scenario import load_scenario


ROOT = Path(__file__).parents[1]
SCENARIO = load_scenario(ROOT / "scenarios/mrr-waterfall")
REPLAY = json.loads(
    (ROOT / "tests/fixtures/operator-b7-run2-current-ask-replay.json").read_text(
        encoding="utf-8"
    )
)


def _script(*turns: object) -> OperatorScript:
    return OperatorScript.from_components(
        SCENARIO.persona,
        SCENARIO.answer_sheet,
        events=SCENARIO.events,
        turns=(SCENARIO.answer_sheet.opening_message, *turns),
        turn_budget=len(turns) + 1,
        phase_by_turn={turn: 7 for turn in range(1, len(turns) + 2)},
    )


def test_run2_lettered_disposition_and_confirmation_beat_recap_terms() -> None:
    bank = MatcherBank(SCENARIO.persona, SCENARIO.answer_sheet)

    ambiguous = bank.reply_for(REPLAY["turn_8_choice"])
    assert ambiguous.rule_id != "persona.source_question"
    for turn in (
        "turn_11_review_choice",
        "turn_15_review_choice",
        "turn_23_review_choice",
        "turn_25_repeated_choice",
        "turn_30_choice",
        "turn_33_yes_a",
        "turn_33_yes_a_question",
        "turn_23_numbered_choice",
    ):
        match = bank.reply_for(REPLAY[turn], context=REPLAY["turn_11_review_choice"])
        assert match.category is Category.DECISION_REQUEST, turn
        assert match.rule_id != "persona.source_question", turn
        assert not match.rule_id.startswith("source.answer."), turn

    # The final question on turn 22 is approval of a newly prepared plan. The
    # earlier review authorization in its recap must not answer that request.
    approval = bank.reply_for(
        REPLAY["turn_22_plan_approval"], context=REPLAY["turn_11_review_choice"]
    )
    assert approval.category is Category.APPROVAL_REQUEST
    assert approval.decision_id != "review_fix_authorization"


def test_run2_source_answer_requires_a_current_source_question() -> None:
    bank = MatcherBank(SCENARIO.persona, SCENARIO.answer_sheet)

    source = bank.reply_for("What is the event id in the supplied source?")
    review = bank.reply_for(
        REPLAY["turn_11_review_choice"], context=REPLAY["turn_11_review_choice"]
    )

    assert source.category is Category.SOURCE_QUESTION
    assert source.rule_id == "source.answer.event id"
    assert review.category is Category.DECISION_REQUEST
    assert not review.rule_id.startswith("source.answer.")


def test_run2_final_addressed_ask_wins_between_source_and_approval() -> None:
    bank = MatcherBank(SCENARIO.persona, SCENARIO.answer_sheet)

    approval = bank.reply_for("What is the event id? Do you approve this plan?")
    source = bank.reply_for("Do you approve this plan? What is the event id?")
    source_after_review = bank.reply_for(
        "The review found a blocking issue. Should I apply the review fix? "
        "What is the event id in the supplied source?"
    )

    assert approval.category is Category.APPROVAL_REQUEST
    assert approval.decision_id is None
    assert source.category is Category.SOURCE_QUESTION
    assert source.rule_id == "source.answer.event id"
    assert source_after_review.rule_id == "source.answer.event id"


def test_run2_review_authorization_is_consumed_before_revised_plan_approval() -> None:
    authorization = SCENARIO.answer_sheet.decision_answers[
        "review_fix_authorization"
    ].answer
    script = _script("Please continue.", "Please continue.", "Please continue.")
    transport = InMemoryTransport(
        [
            TurnResult(agent_message=REPLAY["turn_21_review_repair"]),
            TurnResult(agent_message=REPLAY["turn_22_plan_approval"]),
            TurnResult(agent_message="The revised plan remains pending approval."),
            TurnResult(agent_message="I will wait for your approval."),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[1] == authorization
    assert transport.message_texts[2] != authorization
    assert result.turns[1].delivered_decision_id == "review_fix_authorization"
    assert result.turns[1].match.category is Category.APPROVAL_REQUEST
    assert transport.message_texts.count(authorization) == 1


def test_run2_scheduled_card_waits_for_the_owed_review_disposition() -> None:
    scheduled_card = "Please inspect the published run and its status."
    script = _script(
        {"text": scheduled_card, "substitute_reply": False},
        "Please continue.",
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message=REPLAY["turn_11_review_choice"]),
            TurnResult(agent_message="I will follow the review disposition."),
            TurnResult(agent_message="The review action is underway."),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert result.turns[0].match.category is Category.DECISION_REQUEST
    assert transport.message_texts[1] != scheduled_card
    assert transport.message_texts[2] == scheduled_card


def test_run2_repeated_denominator_challenge_is_bounded_per_topic() -> None:
    ask = "Which source field contains the denominator?"
    script = _script(*("Please continue." for _ in range(5)))
    transport = InMemoryTransport([TurnResult(agent_message=ask) for _ in range(6)])

    result = OperatorEngine(script, transport).run()

    challenges = [
        turn.match.rule_id
        for turn in result.turns
        if turn.match.rule_id == "persona.source_question"
    ]
    assert len(challenges) <= 2
    assert all(
        "denominator" not in reply.casefold() for reply in transport.message_texts[4:]
    )
