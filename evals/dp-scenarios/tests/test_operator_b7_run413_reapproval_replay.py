"""B7 live run r413 (Sonnet, skills main bea68b3d) replay.

r413 lost turns 1-29 to persona stalls before the scripted plan approval
landed, and turns 39-50 to persona stalls after a review-fix reset because
the operator never recognised the agent's re-approval asks as approval
requests at all: ``next_match.category`` never became ``APPROVAL_REQUEST``,
so neither the owed-approval delivery nor ``revision_reapproval_turn`` in
``engine.py`` ever armed, and the run exhausted its 50-turn budget still
waiting at consent -- then was mislabelled ``stop=completed`` instead of a
pending-answer exhaustion.

The root cause was in ``matcher.py``. The agent's re-approval asks used the
literal reply token ("Reply with **Approve** as its own message.", a
bulleted "- **Approve** ...", "1. **You approve the plan.** Reply with
**Approve** as its own message.") rather than the noun
"approval"/"approved" that ``_ADDRESSED_APPROVAL_ASK_PATTERN`` and
``SOLICITATION_PATTERN`` required, and a markdown heading directly above
such a line ("## What clears the blocker\\nReply **Approve** ...") was
never a clause boundary, so the heading's own incidental vocabulary
("blocker", "what") could leak into the ask clause and misroute it to the
review-fix answer instead.

These tests replay exact turn text from
``/private/tmp/dp-b7-sonnet-r413/output/conversation-mrr-waterfall-epoch-1.md``
and assert classification, that the scripted approval fires on the first
genuine ask instead of staying owed indefinitely, that a revision
re-approval fires right after a reset, and that a turn-budget exhaustion
with a still-pending approval ask is no longer mislabelled ``completed``.
"""

from __future__ import annotations

import json
from pathlib import Path

from dp_scenarios.operator.engine import OperatorEngine, OperatorScript, TerminalState
from dp_scenarios.operator.matcher import Category, MatcherBank
from dp_scenarios.operator.transport import InMemoryTransport, ToolCall, TurnResult
from dp_scenarios.scenario import load_scenario

ROOT = Path(__file__).parents[1]
SCENARIO = load_scenario(ROOT / "scenarios/mrr-waterfall")
REPLAY = json.loads(
    (ROOT / "tests/fixtures/operator-b7-run413-reapproval-replay.json").read_text(
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


def _clean(message: str, **kwargs: object) -> TurnResult:
    """A ``TurnResult`` with a clean single provider result, like a real turn."""

    return TurnResult(
        agent_message=message,
        terminal_result_count=1,
        terminal_result_subtype="success",
        terminal_result_is_error=False,
        **kwargs,
    )


def _bank() -> MatcherBank:
    return MatcherBank(SCENARIO.persona, SCENARIO.answer_sheet)


# --- Classification replay: turns 1-5 -------------------------------------


def test_r413_turns_1_to_5_classification() -> None:
    # Turns 1, 2 and 5 are genuine "reply approve" asks (turn 1 offers a
    # compound default-vs-flip choice, turn 5 restates the plan for
    # approval); turns 3 and 4 are not. Turns 1 and 5 used to fall through
    # to decision_request / source_question respectively (persona.*,
    # matched=no) because "Reply **approve**"/"Reply "approve""" never
    # satisfied the old noun-only pattern.
    bank = _bank()
    expected = {
        1: Category.APPROVAL_REQUEST,
        2: Category.APPROVAL_REQUEST,
        3: Category.DECISION_REQUEST,
        4: Category.DECISION_REQUEST,
        5: Category.APPROVAL_REQUEST,
    }
    for n, category in expected.items():
        match = bank.classify(REPLAY[f"turn_{n}_agent"])
        assert match.category is category, n


# --- Classification replay: turns 26-29, the first genuine approval ask --


def test_r413_turns_26_28_29_are_recognised_approval_asks() -> None:
    # Turn 26 ("1. **You approve the plan.** Reply with **Approve** as its
    # own message.") and turn 28 (a bulleted "- **Approve**" option) both
    # used to fall through unmatched, deferring the scripted approval to
    # turn 29 -> 30 (the live run's actual delivery point). All three must
    # now resolve to a genuine, addressed approval request.
    bank = _bank()
    for n in (26, 28, 29):
        match = bank.classify(REPLAY[f"turn_{n}_agent"])
        assert match.category is Category.APPROVAL_REQUEST, n
        assert match.approval_requested, n
        assert match.solicits_operator, n


def test_r413_turn_27_stays_a_decision_request() -> None:
    # Turn 27's actual final ask ("tell me which one [rule]") is a distinct,
    # later question in the same message and must keep owning the reply --
    # the widened approval patterns must not swallow it.
    bank = _bank()
    match = bank.classify(REPLAY["turn_27_agent"])
    assert match.category is Category.DECISION_REQUEST


# --- Classification replay: turns 38-41, the post-reset re-ask -----------


def test_r413_turn_38_is_the_review_fix_authorization_answer() -> None:
    bank = _bank()
    match = bank.classify(REPLAY["turn_38_agent"], context=REPLAY["turn_38_agent"])
    assert match.decision_id == "review_fix_authorization"


def test_r413_turns_40_and_41_are_recognised_approval_asks() -> None:
    # Turns 40-49 all restate "Reply with **Approve** as its own message."
    # or offer it as a bulleted option. None of them contain the noun
    # "approval"/"approved" the old pattern required, so every one of them
    # used to fall through unmatched -- the run never re-approved and
    # stalled for the rest of its budget.
    bank = _bank()
    for n in (40, 41, 42, 48, 49):
        match = bank.classify(REPLAY[f"turn_{n}_agent"])
        assert match.category is Category.APPROVAL_REQUEST, n
        assert match.approval_requested, n
        assert match.solicits_operator, n


# --- Classification replay: turns 49-50, the mislabelled ending ----------


def test_r413_turn_50_heading_does_not_leak_into_the_approval_clause() -> None:
    # Turn 50's ask sits under "## What clears the blocker", which contains
    # both "what" and "blocker" -- vocabulary the review-disposition
    # catch-all keys on. Gluing the heading to the ask clause used to
    # misroute this turn to the review_fix_authorization answer instead of
    # a plain approval request.
    bank = _bank()
    match = bank.classify(REPLAY["turn_50_agent"])
    assert match.category is Category.APPROVAL_REQUEST
    assert match.decision_id != "review_fix_authorization"


def test_r413_turn_budget_exhausted_with_a_pending_approval_is_not_completed() -> None:
    # r413's actual ending: the turn budget is exhausted while the agent's
    # final message (turn 50) is still a genuine, unanswered approval ask.
    # Before the matcher fix this message classified as a source question
    # with solicits_operator=False, so the engine's pending-answer gate
    # never fired and the run was mislabelled ``stop=completed`` despite
    # nothing having been built, reviewed, validated, or published since
    # the reset.
    script = OperatorScript.from_components(
        SCENARIO.persona,
        SCENARIO.answer_sheet,
        events=SCENARIO.events,
        turns=(SCENARIO.answer_sheet.opening_message,),
        turn_budget=1,
        phase_by_turn={1: 7},
    )
    transport = InMemoryTransport([_clean(REPLAY["turn_50_agent"])])

    result = OperatorEngine(script, transport).run()

    assert result.terminal_state is TerminalState.TURN_BUDGET_EXHAUSTED_PENDING_ANSWER


# --- Engine replay: the owed approval and the post-reset re-approval -----


def test_r413_owed_approval_fires_on_first_genuine_ask_then_reapproves_after_reset() -> None:
    """End-to-end replay of both stalls, in one minimal script.

    Turn 1: the scripted approval row is reached while the prior agent
    message asked something else (a source question) -- exactly r413's
    situation from turn ~7 through turn 29, where the script's one
    approval row kept getting swallowed by an open, non-approval question.
    The approval must stay owed rather than firing blind.

    Turn 2: the agent's message is a genuine "reply with Approve" ask in
    r413's own turn-26 shape. The owed approval must fire now -- on the
    first genuine ask -- rather than waiting for turns of misclassification
    (or a forced multi-turn bound).

    Turn 3: the agent reports a reset (with a successful ``reset_workflow``
    tool call), re-binding the plan.

    Turn 4: the agent's message is a genuine post-reset re-approval ask in
    r413's own turn-40 shape. The revision re-approval must fire now,
    resending the exact original approval line, instead of stalling for
    the rest of the run the way turns 40-49 did live.
    """

    approval_text = "Approved: use the defaults as stated."
    approval_row = {"text": approval_text, "substitute_reply": False, "approval": True}
    reset_call = ToolCall(
        name="mcp__nxd-desktop__reset_workflow",
        arguments={"workflow": "workflow"},
        result={"workflow": "workflow", "events": [{"code": "workflow/prepared"}]},
    )

    script = _script(
        approval_row,
        "Please continue.",
        "Please continue.",
        "Please continue.",
    )
    transport = InMemoryTransport(
        [
            _clean("What is the event id in the source?"),
            _clean(REPLAY["turn_26_agent"]),
            _clean(
                "I've applied the authorized correction and reset the "
                "workflow. Tell me what to change.",
                tool_calls=(reset_call,),
            ),
            _clean(REPLAY["turn_40_agent"]),
        ]
    )

    result = OperatorEngine(script, transport).run()
    texts = transport.message_texts

    # Turn 2: the approval row was reached, but the prior ask (turn 1's
    # source question) wasn't approval -- it stays owed and this turn
    # answers the actual question instead of sending "Approved" blind.
    assert texts[1] != approval_text
    # Turn 3: turn 2's genuine "reply with Approve" ask (r413 turn 26's
    # shape) releases the owed approval.
    assert texts[2] == approval_text
    assert result.turns[1].match.category is Category.APPROVAL_REQUEST
    # Turn 5: turn 4's genuine post-reset ask (r413 turn 40's shape)
    # triggers the revision re-approval, resending the same line.
    assert texts[4] == approval_text
    assert result.turns[3].match.category is Category.APPROVAL_REQUEST
