""""Approved" describing data is not a request for the operator's approval.

Live B2 (Luna run 1), turn 4: the agent asked a source question -- "should a
populated `fx_rate` count as approved, or should rows be withheld unless
approval is established elsewhere?" -- and the bare vocabulary scan read it as
an approval request. The engine delivered the owed scripted "Approved." there,
before any plan had been prepared, so intake could not pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import load_answer_sheet
from dp_scenarios.operator.matcher import APPROVAL_REQUEST_PATTERN, Category, MatcherBank
from dp_scenarios.operator.persona import load_persona

ROOT = Path(__file__).parents[1]
PERSONA = load_persona(ROOT / "scenarios/_personas/micromanager.yaml")
FINANCE_CLOSE = load_answer_sheet(ROOT / "scenarios/finance-close/answer-sheet.yaml")

LUNA_RUN1_TURN4 = (
    "I’ll record `b2-weekend-fx` with `exclude_and_warn`, and treat parenthesized "
    "amounts as negative credits.\n\n"
    "The API profile exposes an `fx_rate` field but no separate approval indicator. "
    "For this close, should a populated `fx_rate` count as approved, or should rows "
    "be withheld unless approval is established elsewhere?"
)


def test_a_question_about_whether_data_counts_as_approved_is_not_an_approval_request() -> None:
    result = MatcherBank(PERSONA, FINANCE_CLOSE).reply_for(LUNA_RUN1_TURN4)

    assert result.category is not Category.APPROVAL_REQUEST
    assert result.approval_requested is False


@pytest.mark.parametrize(
    "text",
    [
        "should a populated fx_rate count as approved?",
        "the rate is approved",
        "rows that were approved upstream",
        "no separate approval indicator",
        "unless approval is established elsewhere",
    ],
)
def test_approval_vocabulary_describing_data_is_not_an_ask(text: str) -> None:
    assert APPROVAL_REQUEST_PATTERN.search(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "Do you approve this plan?",
        "Can this plan be approved?",
        "Is the plan approved?",
        "I need your approval to proceed.",
        "Approved.",
        "Can you sign off on the plan?",
    ],
)
def test_genuine_approval_asks_still_match(text: str) -> None:
    assert APPROVAL_REQUEST_PATTERN.search(text) is not None
