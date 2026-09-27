"""Review-repair authorization asks from live B2 (Luna run 2).

After an indeterminate review flagged three blockers, the agent asked to
*repair* them -- "May I repair the cents and diagnostic-count issues?",
"Please explicitly authorize these review findings for repair: ...", "Please
explicitly approve `status-confirmation`, `signed-cents`, and
`diagnostic-counts`". None routed to the declared review-fix authorization:
"repair" was not a fix verb, and "please explicitly authorize/approve" was
not an ask at all, so the operator answered with status and source facts for
eleven turns and nothing was rebuilt.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import load_answer_sheet
from dp_scenarios.operator.matcher import Category, MatcherBank
from dp_scenarios.operator.persona import load_persona

ROOT = Path(__file__).parents[1]
FIXTURES = json.loads(
    (ROOT / "tests/fixtures/operator-b2-luna-run2-repair-asks.json").read_text()
)
PERSONA = load_persona(ROOT / "scenarios/_personas/micromanager.yaml")
FINANCE_CLOSE = load_answer_sheet(ROOT / "scenarios/finance-close/answer-sheet.yaml")
REVIEW_CONTEXT = FIXTURES["b2_luna_run2_turn3_review_blockers"]


@pytest.mark.parametrize(
    "key",
    [
        "b2_luna_run2_turn3_review_blockers",
        "b2_luna_run2_turn4_authorize_for_repair",
        "b2_luna_run2_turn7_approve_ids",
        "b2_luna_run2_turn9_no_authorization_yet",
    ],
)
def test_live_repair_asks_route_to_the_review_fix_answer(key: str) -> None:
    result = MatcherBank(PERSONA, FINANCE_CLOSE).reply_for(
        FIXTURES[key], context=REVIEW_CONTEXT
    )

    assert result.category is Category.DECISION_REQUEST
    assert result.rule_id == "decision.answer.review_fix_authorization"


@pytest.mark.parametrize(
    "message",
    [
        "Please explicitly approve the plan so I can build it.",
        "Please approve the blueprint.",
    ],
)
def test_plan_approval_without_review_findings_stays_an_approval_request(
    message: str,
) -> None:
    result = MatcherBank(PERSONA, FINANCE_CLOSE).reply_for(message)

    assert result.category is Category.APPROVAL_REQUEST
