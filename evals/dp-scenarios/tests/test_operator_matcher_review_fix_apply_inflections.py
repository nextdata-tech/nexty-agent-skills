"""Regression tests for review-fix authorization wording from live B2 run 15."""

from __future__ import annotations

from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import load_answer_sheet
from dp_scenarios.operator.matcher import Category, MatcherBank
from dp_scenarios.operator.persona import load_persona

ROOT = Path(__file__).parents[1]
PERSONA = load_persona(ROOT / "scenarios/_personas/micromanager.yaml")
FINANCE_CLOSE = load_answer_sheet(ROOT / "scenarios/finance-close/answer-sheet.yaml")

REVIEW_FINDING_CONTEXT = (
    "The latest review found that the previous fix was incomplete and raised "
    "two more crash risks. The agent listed the proposed fixes for those findings."
)

B2_TURN9_ENUMERATED_FIX_CHOICE = (
    "The latest review round found the previous fix was incomplete and surfaced "
    "two more crash risks, plus a lower-confidence third one.\n\n"
    "**Proposed fixes**, none changing any decision: coerce `close_date` to a "
    "string, handle a missing `amount` with a clear error, and treat an "
    "unparseable `fx_rate` as missing.\n\n"
    "None of the three touch any model, decision, threshold, or assert — "
    "they're all about not crashing on inputs the blueprint already said "
    "could vary. Do you want me to proceed with all three, some subset, or none?"
)


@pytest.mark.parametrize(
    ("message", "context"),
    [
        (
            "**Do you approve applying both fixes and recapturing?**",
            REVIEW_FINDING_CONTEXT,
        ),
        (
            "**Do you approve applying these three fixes and recapturing?**",
            REVIEW_FINDING_CONTEXT,
        ),
        (B2_TURN9_ENUMERATED_FIX_CHOICE, ""),
        ("Approve applying these two as well?", REVIEW_FINDING_CONTEXT),
        (
            "**Do you approve applying these two changes and recapturing?** "
            "A yes/no is all I need.",
            REVIEW_FINDING_CONTEXT,
        ),
        (
            "Please reply with a plain **yes** (apply both), **no** "
            "(apply neither), or tell me which one specifically if you only "
            "want one.",
            REVIEW_FINDING_CONTEXT,
        ),
    ],
    ids=["turn7", "turn8", "turn9_enumerated_choice", "turn10", "turn11", "turn12"],
)
def test_live_review_fix_authorization_asks_route_to_the_declared_answer(
    message: str, context: str
) -> None:
    bank = MatcherBank(PERSONA, FINANCE_CLOSE)

    result = bank.reply_for(message, context=context)

    assert result.category is Category.DECISION_REQUEST
    assert result.rule_id == "decision.answer.review_fix_authorization"
    assert result.decision_id == "review_fix_authorization"
    assert (
        result.reply
        == FINANCE_CLOSE.decision_answers["review_fix_authorization"].answer
    )


@pytest.mark.parametrize(
    "message",
    [
        "Do you approve this spec?",
        "Approve the blueprint?",
        "**Do you approve this spec?** A yes/no is all I need.",
        "Do you approve applying this spec to the build?",
    ],
    ids=["spec-approval", "blueprint-approval", "bold-spec-approval", "apply-spec"],
)
def test_spec_and_blueprint_approval_stays_an_approval_request(message: str) -> None:
    bank = MatcherBank(PERSONA, FINANCE_CLOSE)

    result = bank.reply_for(message, context=REVIEW_FINDING_CONTEXT)

    # The micromanager persona overrides the generic approval reply, so the
    # rule id carries its ``persona.`` prefix.
    assert result.category is Category.APPROVAL_REQUEST
    assert result.rule_id == "persona.approval_request"
    assert result.decision_id is None


def test_enumerated_proceed_choice_needs_a_fix_list() -> None:
    bank = MatcherBank(PERSONA, FINANCE_CLOSE)
    message = (
        "A review found three items in the blueprint. Do you want me to proceed "
        "with all three, some subset, or none?"
    )

    result = bank.reply_for(message)

    assert result.decision_id != "review_fix_authorization"
    assert result.rule_id != "decision.answer.review_fix_authorization"
