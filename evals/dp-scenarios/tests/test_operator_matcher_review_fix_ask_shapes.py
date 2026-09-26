"""Regression tests for B2 live run 10's stalled review-fix authorization asks.

Live run 10 (finance-close) asked the operator, across several turns, to
authorize a reported review fix ("Do you authorize that fix?", "fix the
crash -- yes or no?", "authorize catching the parse error ...? (yes/no)",
"fix it (...) -- yes or no?"). None of these were recognized by
``_review_fix_request``'s action/choice patterns, or -- for the
bold-wrapped and dash-appended shapes -- were not even extracted as an ask
clause at all, so the operator fell back to "I don't know, you tell me" and
the run stalled without ever authorizing the review's own reported fix.

Each fixture below is a compact excerpt of the actual live turn, trimmed to
the sentence(s) that matter for routing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import load_answer_sheet
from dp_scenarios.operator.matcher import Category, MatcherBank
from dp_scenarios.operator.persona import load_persona

ROOT = Path(__file__).parents[1]
PERSONA = load_persona(ROOT / "scenarios/_personas/micromanager.yaml")
FINANCE_CLOSE = load_answer_sheet(ROOT / "scenarios/finance-close/answer-sheet.yaml")

# Live turn 5: the finding is reported in the same message as the ask, and the
# ask names its fix only as a gerund ("authorize fixing #1"), which a bare
# ``\bfix\b`` boundary does not match.
B2_TURN5_AUTHORIZE_FIXING_GERUND = (
    "A fresh review found one new issue: a garbage FX rate still crashes "
    "the whole build instead of excluding just that row.\n\n"
    "Do you authorize fixing #1 (catch the parse error and exclude/flag "
    "that row instead of crashing)?"
)

# Live turn 6: the finding was reported on an earlier turn (context), and the
# ask itself is wrapped in markdown bold, which broke the question-clause-end
# check ("fix?**" does not end in a bare "?").
B2_TURN6_BOLD_WRAPPED_AUTHORIZE = (
    "I can't accept \"I don't know, you tell me\" as a decision here.\n\n"
    "**On the crash bug**: my recommendation is simply to catch the parse "
    "failure and treat that row the same as a blank rate. "
    "**Do you authorize that fix?**"
)

# Live turn 7: the ask names its fix only by verb ("authorize catching the
# parse error"), never the noun "fix", and closes with a parenthetical
# "(yes/no)" rather than the question mark itself.
B2_TURN7_AUTHORIZE_CATCHING_YESNO = (
    "1. The crash bug -- authorize catching the parse error so that row "
    "gets excluded-and-flagged instead of aborting the whole build? (yes/no)"
)

# Live turn 10: a bare "fix it ... -- yes or no?" with no "authorize" verb at
# all, and the connective is "or" rather than "/".
B2_TURN10_FIX_IT_YES_OR_NO = (
    "- Crash bug: fix it (catch the error, exclude-and-flag that row) -- "
    "yes or no?"
)

# The finding context these asks depend on, standing in for the earlier turn
# it was actually reported on (the review-fix branch accepts finding context
# from either the message itself or this ``context`` argument).
B2_REVIEW_FINDING_CONTEXT = (
    "A fresh review of the corrected build found one new issue: a garbage "
    "FX rate still crashes the entire build instead of excluding just that "
    "row."
)


@pytest.mark.parametrize(
    ("fixture", "context"),
    [
        (B2_TURN5_AUTHORIZE_FIXING_GERUND, ""),
        (B2_TURN6_BOLD_WRAPPED_AUTHORIZE, B2_REVIEW_FINDING_CONTEXT),
        (B2_TURN7_AUTHORIZE_CATCHING_YESNO, B2_REVIEW_FINDING_CONTEXT),
        (B2_TURN10_FIX_IT_YES_OR_NO, B2_REVIEW_FINDING_CONTEXT),
    ],
    ids=["turn5_gerund", "turn6_bold_wrapped", "turn7_verb_only_yesno", "turn10_bare_fix_it"],
)
def test_review_fix_authorize_asks_route_to_the_declared_authorization(
    fixture: str, context: str
) -> None:
    bank = MatcherBank(PERSONA, FINANCE_CLOSE)

    result = bank.reply_for(fixture, context=context)

    assert result.category is Category.DECISION_REQUEST
    assert result.rule_id == "decision.answer.review_fix_authorization"
    assert result.decision_id == "review_fix_authorization"
    assert (
        result.reply
        == FINANCE_CLOSE.decision_answers["review_fix_authorization"].answer
    )


def test_a_specific_declared_decision_named_in_the_ask_still_wins() -> None:
    """The specificity rule survives: an explicit fix action still wins over
    recap terms, but a decision *named in the actual ask clause itself* --
    not merely recapped in surrounding prose -- must still take priority over
    the generic authorization.
    """

    bank = MatcherBank(PERSONA, FINANCE_CLOSE)
    # weekend_fx terms are "weekend" and "rate"; naming both inside the ask
    # clause itself must resolve to that specific decision, not the generic
    # review-fix authorization, even with finding context present.
    message = (
        "A review found one issue. Do you authorize applying the fix for the "
        "weekend rate row?"
    )

    result = bank.reply_for(message, context=B2_REVIEW_FINDING_CONTEXT)

    assert result.decision_id == "weekend_fx"


def test_plain_review_narration_is_not_read_as_an_authorization_ask() -> None:
    """Status narration that merely reports a review finding, with no actual
    ask clause, must not be misrouted as an authorization request.
    """

    bank = MatcherBank(PERSONA, FINANCE_CLOSE)
    narration = (
        "The review found two issues in the closure. I am continuing to work "
        "on fixes and will report back once they are resolved."
    )

    result = bank.reply_for(narration)

    assert result.decision_id != "review_fix_authorization"


def test_a_non_review_yes_no_question_is_not_read_as_an_authorization_ask() -> None:
    """A bare "yes or no" question with no review-finding context anywhere
    must not be captured by the broadened review-fix action pattern.
    """

    bank = MatcherBank(PERSONA, FINANCE_CLOSE)
    message = "Should we use USD or EUR for the display currency -- yes or no?"

    result = bank.reply_for(message)

    assert result.decision_id != "review_fix_authorization"


def test_a_non_review_fix_request_without_finding_context_is_not_authorization() -> None:
    """"Fix ... yes or no?" alone, with no review-finding context declared
    anywhere (not in the message, not in the carried-forward context), must
    not resolve as the review-fix authorization -- that decision requires an
    actual reported review finding, not just the fix vocabulary.
    """

    bank = MatcherBank(PERSONA, FINANCE_CLOSE)
    message = "Please fix the typo in the README -- yes or no?"

    result = bank.reply_for(message)

    assert result.decision_id != "review_fix_authorization"
