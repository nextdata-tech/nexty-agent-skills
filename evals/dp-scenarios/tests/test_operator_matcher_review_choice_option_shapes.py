"""Regression tests for the B11 r409 live run's undetected review-choice asks.

Live run /private/tmp/dp-b11-sonnet-r409 (crm-pipeline-drift, scripted operator,
persona anxious-non-decider) hit a blocking review finding
(``updated-at-format-ruling-undisclosed``) with two labelled options and a
named recommendation. Turn 12's ask ("tell me A or B ... and approve ... by
ID") was not recognized as a review choice at all, so the operator fell to
``persona.approval_request`` instead of accepting the recommended option, and
turn 13's near-identical follow-up repeated the miss. Turns 14-16 are the
downstream symptom -- with the fix, the run would have accepted "option A" at
turn 12 and never reached them.

Two independent shape gaps caused the miss, both in
``dp_scenarios.operator.matcher``:

1. The offered alternatives were bold-markdown list items ("- **A: ... "
   "(recommended).**") and, on the follow-up turn, a markdown table row
   ("| **A: ...** | ... |"). ``_REVIEW_ALTERNATIVES_PATTERN`` and
   ``_REVIEW_OFFERED_LABEL_PATTERN`` only recognized a bare bullet/number
   directly at the start of a line, so neither markdown shape was read as
   offering labelled alternatives at all.
2. The actual ask clause ("tell me A or B, ... and approve ... by ID") names
   the offered labels directly rather than using a choice noun/verb
   ("option", "choice", "choose", "which"), so ``_explicit_review_choice``'s
   keyword check never fired even once alternatives were recognized.
3. The recommendation itself was marked with a trailing "(recommended)" on
   the option's own line ("A: ISO 8601 ... (recommended).") rather than a
   leading "I recommend ..." phrase, which the original
   ``_REVIEW_RECOMMENDATION_PATTERN`` could not see at all.

Each fixture below is trimmed to the sentence(s) that matter for routing, and
the two-way markdown/table shapes are excerpted verbatim (sanitized: no
customer data, this is a synthetic scenario transcript).
"""

from __future__ import annotations

from pathlib import Path

from dp_scenarios.operator.answer_sheet import load_answer_sheet
from dp_scenarios.operator.matcher import Category, MatcherBank
from dp_scenarios.operator.persona import load_persona

ROOT = Path(__file__).parents[1]
PERSONA = load_persona(ROOT / "scenarios/_personas/anxious-non-decider.yaml")
CRM_PIPELINE_DRIFT = load_answer_sheet(
    ROOT / "scenarios/crm-pipeline-drift/answer-sheet.yaml"
)
RECOMMENDED_A_REPLY = "Go with option A, as you recommend."

# Turn 12: the blocking finding is reported in the same message as the ask.
# The two options are a bold-wrapped, dash-bulleted list, and the
# recommendation marker trails the label on the option's own line rather
# than leading a separate "I recommend" sentence.
B11_TURN12_BOLD_LIST_TRAILING_RECOMMENDED = """
The fresh review of generation 2 found one blocking issue, so nothing is
validated, published or queried. I haven't edited, reset or recaptured
anything, and I won't until you decide on the blocking finding.

**Blocking: `updated-at-format-ruling-undisclosed`**
- **The problem.** The plan doesn't say how updatedAt is ordered, but the
  transform has to pick the latest version of each deal.
- **Proposed fix.** Amend the blueprint and decisions to state one rule.
  - **A: ISO 8601 with an offset only (recommended).** Any other value fails
    the build.
  - **B: the current behaviour, written down.** Epoch numbers above 1e11
    mean milliseconds, other numbers mean seconds, and timezone-less strings
    mean UTC.

**To continue:** tell me A or B, or give the actual updatedAt format, and
approve `updated-at-format-ruling-undisclosed` by ID. I'll then record that
decision in the ledger, reset, and amend the blueprint with your choice.
"""

# Turn 13: the same finding, restated after the operator stalled. The two
# options are now rows of a markdown table (not a bulleted list at all), and
# the recommendation is a separate "I recommend A." sentence.
B11_TURN13_TABLE_SHAPED_OPTIONS = """
The finding is real but narrow. Whether it matters depends on one thing I
can't see: what format the source uses for updatedAt.

**The two options**
| | Risk if the source format is what you expect | Risk if it isn't |
|---|---|---|
| **A: ISO 8601 with offset only** | none | the build fails loudly naming the value |
| **B: current guessing, written down** | none | wrong versions can be kept silently |

I recommend A. It can cost a round, but it can't publish wrong numbers
without telling you.

The review report is a blocking finding. Publication needs a clear fresh
review after a reset.

I haven't changed anything. When you're ready, tell me A or B (or the real
format) and approve `updated-at-format-ruling-undisclosed` by ID, and I'll
proceed as described.
"""

# Turn 11: the immediately preceding turn -- a plan-approval ask with no
# offered review-finding alternatives at all. Regression check that widening
# review-choice detection did not turn a plain approval ask into one.
B11_TURN11_PLAN_APPROVAL_NO_ALTERNATIVES = """
The amended plan is bound and awaiting your approval. The reset worked and
the consent request for the new generation is pending. I haven't
regenerated or recaptured anything, and I won't until you approve.

**The amended blueprint**
- **Current rows.** One row per deal, from its most recent version.
- **Status.** Landed as an internal-only column with no query role.

**To continue:** reply with an explicit approval such as "Approved,
proceed." Anything else, including answers or corrections, won't count as
approval.
"""

# Turn 14: the operator stalled again and the agent switched to offering a
# *different*, unrelated numbered menu of clarifying topics -- it repeats
# "Option A (recommended)" / "Option B" in a recap sentence, but the actual
# ask ("Which part isn't clear yet?") does not name either offered label.
# This must stay unmatched as a review choice: recap language mentioning the
# options is not the same as the ask addressing them.
B11_TURN14_UNRELATED_CLARIFYING_MENU = """
I covered the risk in my last message, so I won't repeat it. In short:

- **What the choice does.** Option A (recommended) fails loudly instead of
  guessing. Option B keeps the guessing and writes it down.

Which part isn't clear yet? I can go deeper on any of these:
1. How a wrong pick would look.
2. What A costs if it fails.
3. Whether the other unverified items matter.
4. What "stop here" leaves behind.
"""


def test_turn12_bold_list_with_trailing_recommended_marker_routes_to_review_choice() -> None:
    bank = MatcherBank(PERSONA, CRM_PIPELINE_DRIFT)

    result = bank.reply_for(B11_TURN12_BOLD_LIST_TRAILING_RECOMMENDED)

    assert result.category is Category.DECISION_REQUEST
    assert result.rule_id == "review.choice_undeclared"
    assert result.reply == RECOMMENDED_A_REPLY
    assert "option A" in result.reply


def test_turn13_table_shaped_options_route_to_review_choice() -> None:
    bank = MatcherBank(PERSONA, CRM_PIPELINE_DRIFT)

    result = bank.reply_for(B11_TURN13_TABLE_SHAPED_OPTIONS)

    assert result.category is Category.DECISION_REQUEST
    assert result.rule_id == "review.choice_undeclared"
    assert result.reply == RECOMMENDED_A_REPLY
    assert "option A" in result.reply


def test_turn11_plan_approval_with_no_offered_alternatives_still_gets_approval() -> None:
    """A turn that genuinely needs approval -- not a review choice -- must
    still route to the persona's approval reply after the widening."""

    bank = MatcherBank(PERSONA, CRM_PIPELINE_DRIFT)

    result = bank.reply_for(B11_TURN11_PLAN_APPROVAL_NO_ALTERNATIVES)

    assert result.category is Category.APPROVAL_REQUEST
    assert result.rule_id == "persona.approval_request"


def test_turn14_recap_mentioning_options_without_addressing_them_is_not_a_review_choice() -> None:
    """The ask itself ("Which part isn't clear yet?") names neither offered
    label, so recap language elsewhere in the message must not manufacture a
    review choice out of an unrelated clarifying-menu ask."""

    bank = MatcherBank(PERSONA, CRM_PIPELINE_DRIFT)

    result = bank.reply_for(B11_TURN14_UNRELATED_CLARIFYING_MENU)

    assert result.rule_id != "review.choice_undeclared"


def test_non_review_decision_with_a_stated_recommendation_is_not_auto_accepted() -> None:
    """The boundary the fix must respect: recommendation-acceptance is scoped
    to a review finding/choice in play. A plain business decision that
    happens to carry a labelled recommendation -- with no review finding
    anywhere in context -- must still defer to the persona's own decision
    tactic (anxious-non-decider refuses risk-bearing decisions and asks
    back), never silently accept the recommended option by name."""

    bank = MatcherBank(PERSONA, CRM_PIPELINE_DRIFT)
    message = (
        "We could either keep the nightly refresh cadence or switch to "
        "hourly polling.\n\n"
        "- A: keep the nightly cadence (recommended). Simpler operationally.\n"
        "- B: switch to hourly polling. More current, more API load.\n\n"
        "Tell me A or B and I'll proceed."
    )

    result = bank.reply_for(message)

    assert result.rule_id != "review.choice_undeclared"
    assert result.reply != RECOMMENDED_A_REPLY
