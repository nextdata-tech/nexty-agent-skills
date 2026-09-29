"""Clause selection: r416 replays for B7, B5 and B1.

One rule: the message's active ask is its latest genuine ask. Conditional
revision offers, optional "say which and I'll amend" trailers, and status-only
sentences never displace an earlier explicit ask, and a declared decision named
in an earlier genuine question is still answered when the active clause names
none.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.operator.matcher import Category, MatcherBank, solicits_operator
from dp_scenarios.scenario import load_scenario

ROOT = Path(__file__).parents[1]
REPLAY = json.loads(
    (ROOT / "tests/fixtures/operator-r416-clause-selection-replay.json").read_text(encoding="utf-8")
)


def _bank(scenario_id: str) -> MatcherBank:
    scenario = load_scenario(ROOT / "scenarios" / scenario_id)
    return MatcherBank(scenario.persona, scenario.answer_sheet)


# --- B7 turn 4: the declared same-month question is not the last clause -----


def test_b7_turn_4_delivers_the_declared_same_month_decision() -> None:
    match = _bank("mrr-waterfall").reply_for(
        REPLAY["b7_turn_4_same_month_ask"], available_event_ids=("B7-same-month",)
    )

    assert match.category is Category.DECISION_REQUEST
    assert match.decision_id == "same_month_classification"
    assert match.rule_id == "decision.answer.same_month_classification"
    assert match.matched


def test_b7_declared_question_survives_an_unrecognised_trailing_invitation() -> None:
    # The trailing sentence is not one of the recognised optional-offer
    # shapes, so it stays the active clause and names no declared decision.
    # The genuine question earlier in the same message must still answer.
    text = REPLAY["b7_turn_4_same_month_ask"].replace(
        "Tell me which if it matters to you.", "Whichever suits you is fine by me."
    ).replace("If you choose B, one more rule is needed.", "Please pick one of them.")
    match = _bank("mrr-waterfall").reply_for(text, available_event_ids=("B7-same-month",))

    assert match.decision_id == "same_month_classification"


def test_b7_declared_decision_is_not_answered_before_its_event() -> None:
    match = _bank("mrr-waterfall").reply_for(REPLAY["b7_turn_4_same_month_ask"])
    assert match.decision_id != "same_month_classification"


# --- B5: an earlier approval ask is not hijacked by a trailing offer ---------


@pytest.mark.parametrize("turn", ["4", "6", "7", "11"])
def test_b5_explicit_approval_asks_survive_trailing_amend_offers(turn: str) -> None:
    match = _bank("inventory-position").reply_for(REPLAY["b5"][turn])

    assert match.category is Category.APPROVAL_REQUEST
    assert match.solicits_operator


def test_b5_bold_lead_in_reply_ask_is_a_solicitation() -> None:
    # "**To proceed:** reply ..." has emphasis between the colon and the space.
    assert solicits_operator('**To proceed:** reply "Yes, do A plus B."')
    assert solicits_operator("Some text.\n**Reply with an explicit approval.**")
    match = _bank("inventory-position").reply_for(REPLAY["b5"]["9"])
    assert match.decision_id == "review_fix_authorization"


def test_b5_direct_choice_outranks_a_trailing_status_sentence() -> None:
    match = _bank("inventory-position").reply_for(REPLAY["b5"]["8"])

    assert match.matched_request_clause is not None
    assert match.matched_request_clause.startswith("Please tell me which option you want")


@pytest.mark.parametrize("turn", ["1", "2"])
def test_b5_unchanged_turns_stay_approval_asks(turn: str) -> None:
    match = _bank("inventory-position").reply_for(REPLAY["b5"][turn])
    assert match.category is Category.APPROVAL_REQUEST


def test_b5_turn_10_is_still_the_review_fix_authorization() -> None:
    match = _bank("inventory-position").reply_for(REPLAY["b5"]["10"])
    assert match.decision_id == "review_fix_authorization"


def test_a_lone_optional_offer_or_status_sentence_is_still_the_active_ask() -> None:
    from dp_scenarios.operator.matcher import _active_request_clauses

    assert _active_request_clauses("If any answer differs, say which, and I'll amend the plan first.") == [
        "If any answer differs, say which, and I'll amend the plan first."
    ]
    status = "The findings are awaiting your decision."
    assert _active_request_clauses(status) == [status]
    # Approval status is the approval ask itself and is never demoted.
    approval = "Please review the plan. I am awaiting your approval."
    assert _active_request_clauses(approval)[-1] == "I am awaiting your approval."


# --- B1: negated "say which" is a limit, not an ask ---------------------------


def test_b1_negated_say_which_is_not_a_solicitation() -> None:
    sentence = "The check passed on the last attempt, so I can't say which fix resolved it."
    assert not solicits_operator(sentence)
    for text in (sentence, "I cannot say whether it was the retry.", "I couldn't say if that helped.",
                 "I won’t say which."):
        assert not solicits_operator(text), text
    for turn in ("turn_19_negated_say_which", "turn_24_negated_say_which"):
        assert not solicits_operator(REPLAY["b1"][turn]), turn
        match = _bank("crm-pipeline").reply_for(REPLAY["b1"][turn])
        assert match.category is not Category.DECISION_REQUEST, turn
        assert not match.solicits_operator, turn


def test_b1_addressed_say_which_is_still_a_solicitation() -> None:
    assert solicits_operator("Please say which option you want.")
    assert solicits_operator("Say which one you prefer.")
    assert solicits_operator("If any answer differs, say which.")
