"""Regression tests for the "owed approval" reconfirmation mechanism.

B2's live run6 transmitted its scripted ``approval: true`` turn while the
agent's previous message was only a clarifying question -- nothing had
actually been asked for approval yet. Every later genuine "Do you approve
...?" ask then misrouted (see the matcher fixes in
``test_operator_matcher_b2b5_regressions.py``), and even once routing was
fixed, the operator's canned "What exactly am I approving?" persona line
demanded specifics the agent had already supplied, over and over.

The scripted approval still transmits at its declared slot when the agent's
last message asked nothing, or asked for approval. When that message asks the
operator something else (a clarifying question), or a declared decision answer
is pending, the slot is owed instead and delivered at the next genuine approval
ask: an "Approved." sent in answer to a question lands before any plan exists
(B2 run17: ``intake_workflow_prepare_not_before_approval``). For an approval
that did go out early to a statement, the engine remembers the text, and the
first time afterward that the agent genuinely asks for approval, it reconfirms
that same text verbatim instead of running the ordinary matcher/persona path.
This never mints a second ``spec_approved`` row and fires at most once per run.
"""

from __future__ import annotations

import json
from pathlib import Path

from dp_scenarios.operator.answer_sheet import load_answer_sheet
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.events import load_event_cards
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult

from test_operator_engine import make_script  # type: ignore[import-not-found]


ROOT = Path(__file__).parents[1]
FIXTURES = json.loads(
    (ROOT / "tests/fixtures/operator-matcher-b2b5-regressions.json").read_text(
        encoding="utf-8"
    )
)
PERSONA = load_persona(ROOT / "scenarios/_personas/micromanager.yaml")
FINANCE_CLOSE = load_answer_sheet(ROOT / "scenarios/finance-close/answer-sheet.yaml")
FINANCE_CLOSE_EVENTS = load_event_cards(ROOT / "scenarios/finance-close/events.yaml")


def _spec_approved_rows(result: object) -> list[dict]:
    return [row for row in result.ledger_rows if row.get("action_kind") == "spec_approved"]  # type: ignore[attr-defined]


def _claim(result: object, turn_index: int) -> dict:
    return result.ledger_rows[turn_index].get("claim") or {}  # type: ignore[attr-defined]


def test_an_early_scripted_approval_is_reconfirmed_once_then_falls_back_to_the_persona_line() -> None:
    """The owed approval is delivered verbatim on the first genuine ask, and only once."""

    script = make_script(
        turns=(
            "Improve weekly visibility.",
            "Please continue.",
            {"text": "Approved. Proceed.", "approval": True, "substitute_reply": False},
            "Please continue again.",
            "Please continue once more.",
            "Please continue yet again.",
        )
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Which milestone is next?"),
            # A status line before the scripted approval turn: no approval was
            # asked for yet, and no question is open (an open question would
            # defer the approval instead; see the deferral tests below).
            TurnResult(agent_message="Still drafting the plan."),
            TurnResult(agent_message="Building now."),
            # The first genuine approval ask after the early approval.
            TurnResult(agent_message="Do you approve this plan?"),
            # A second genuine approval ask: reconfirmation is already spent.
            TurnResult(agent_message="Do you approve this plan?"),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[2] == "Approved. Proceed."
    assert transport.message_texts[4] == "Approved. Proceed."
    assert transport.message_texts[5] == "Yes, please continue."

    approvals = _spec_approved_rows(result)
    assert len(approvals) == 1
    assert approvals[0]["turn"] == 3
    assert approvals[0]["artifact_ref"] == "Approved. Proceed."
    assert _claim(result, 4).get("approval_reconfirmed") is True
    assert "approval_reconfirmed" not in _claim(result, 5)


def test_an_approval_answering_a_genuine_ask_is_never_resent() -> None:
    """Nothing is owed when the scripted approval already answered a real ask."""

    script = make_script(
        turns=(
            "Improve weekly visibility.",
            "Please continue.",
            {"text": "Approved. Go ahead.", "approval": True, "substitute_reply": False},
            "Please continue again.",
            "Please continue once more.",
        )
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Which milestone is next?"),
            # A genuine approval ask right before the scripted approval turn.
            TurnResult(agent_message="Do you approve this plan?"),
            TurnResult(agent_message="Do you approve this plan?"),
            TurnResult(agent_message="Do you approve this plan?"),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[3] == "Yes, please continue."
    assert transport.message_texts[4] == "Yes, please continue."
    assert "Approved. Go ahead." not in (transport.message_texts[3], transport.message_texts[4])

    approvals = _spec_approved_rows(result)
    assert len(approvals) == 1
    assert approvals[0]["turn"] == 3
    for index in range(len(result.ledger_rows)):
        assert "approval_reconfirmed" not in _claim(result, index)


def test_a_pending_decision_answer_keeps_priority_over_reconfirmation() -> None:
    """A decision reply goes out first; the owed approval survives to fire later."""

    script = make_script(
        turns=(
            "Improve weekly visibility.",
            "Please continue.",
            {"text": "Approved. Proceed.", "approval": True, "substitute_reply": False},
            "Please continue again.",
            "Please continue once more.",
            "Please continue further.",
        )
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Which milestone is next?"),
            TurnResult(agent_message="Still drafting the plan."),
            TurnResult(agent_message="Building now."),
            # This message carries the declared decision term *and* approval
            # vocabulary in the same breath; the decision must still win.
            TurnResult(agent_message="Which option should I pick, and do you approve?"),
            # Nothing pending now: the owed approval is still there.
            TurnResult(agent_message="Do you approve this plan?"),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[4] == "Yes."
    assert transport.message_texts[5] == "Approved. Proceed."
    assert "approval_reconfirmed" not in _claim(result, 4)
    assert _claim(result, 5).get("approval_reconfirmed") is True
    assert len(_spec_approved_rows(result)) == 1


def test_b2_shaped_replay_reconfirms_at_the_first_real_approval_ask() -> None:
    """Turns 1-4 of B2 run6: the early scripted approval is reconfirmed at turn 4.

    Turn 1 is a clarifying question with no approval solicited; the scripted
    approval at turn 3 still transmits unconditionally (unchanged pinned
    behavior). Turn 4's actual "Do you approve this plan ... data product?"
    (the exact live shape that used to misroute to ``decision.answer.weekend_fx``)
    is the first genuine ask, so it gets the reconfirmation verbatim rather
    than a fresh decision lookup or the persona's demand for specifics.
    """

    turns = FINANCE_CLOSE.turns[:4]
    script = OperatorScript.from_components(
        PERSONA,
        FINANCE_CLOSE,
        turns=turns,
        turn_budget=len(turns),
        phase_by_turn={1: 1, 2: 2, 3: 3, 4: 4},
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Ready to inspect the close."),
            TurnResult(agent_message="Ready to inspect the close."),
            TurnResult(agent_message=FIXTURES["b2_turn3_approve_the_plan_question"]),
        ]
    )

    result = OperatorEngine(script, transport).run()

    approval_text = turns[2]["text"] if isinstance(turns[2], dict) else turns[2]
    assert transport.message_texts[2] == approval_text
    assert transport.message_texts[3] == approval_text
    approvals = _spec_approved_rows(result)
    assert len(approvals) == 1
    assert approvals[0]["turn"] == 3
    assert _claim(result, 3).get("approval_reconfirmed") is True


# ---------------------------------------------------------------------------
# The "owed approval" defer mechanism.
#
# B2's live run7 hit a different failure than run6's: the scripted
# ``approval: true`` turn landed while a *decision* answer was pending (from
# an unrelated weekend-FX question), so ``defer_scheduled_approval`` correctly
# chose to send the decision reply instead -- but the approval text itself was
# then simply dropped. Intake failed with ``intake_spec_approval_missing`` and
# every later "Do you approve?" got the persona's "What exactly am I
# approving?" forever, because the reconfirmation mechanism above only arms
# when an approval was actually transmitted early; here nothing was ever
# transmitted at all.
#
# The fix below keeps the deferred approval's text owed until it can actually
# be sent: at the next turn where the agent's previous message is a genuine
# approval request (and no decision answer is pending, and a dynamic
# reapproval is not itself firing), the owed text goes out as a real approval
# turn -- minting the ``spec_approved`` row for the first time, not a
# reconfirmation. If nothing genuine comes up, a three-turn bound forces it
# through at the next turn that is not itself carrying a pending decision, so
# a run can never simply lose its declared approval.
# ---------------------------------------------------------------------------


def test_a_deferred_approval_is_delivered_at_the_next_genuine_approval_ask() -> None:
    """The owed approval fires the first time the agent genuinely asks again."""

    turns = (
        "Improve weekly visibility.",
        "Please continue.",
        {"text": "Approved. Proceed.", "approval": True, "substitute_reply": False},
        "Please continue again.",
        "Please continue once more.",
    )
    script = make_script(turns=turns)
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Status update."),
            # Sets up a pending decision answer for the scripted approval turn.
            TurnResult(agent_message="Which option should I pick?"),
            # The deferred turn sent the decision reply instead of the
            # approval; this is the first genuine ask afterward.
            TurnResult(agent_message="Do you approve this plan?"),
            TurnResult(agent_message="Building now."),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[2] == "Yes."
    assert transport.message_texts[3] == "Approved. Proceed."

    approvals = _spec_approved_rows(result)
    assert len(approvals) == 1
    assert approvals[0]["turn"] == 4
    assert approvals[0]["artifact_ref"] == "Approved. Proceed."
    assert _claim(result, 3).get("approval_deferred_for_decision") is True
    # This was a genuine ask, fully answered by the owed delivery -- nothing
    # is left to reconfirm afterward.
    assert "approval_reconfirmed" not in _claim(result, 4)


def test_a_pending_decision_still_goes_first_ahead_of_an_owed_approval() -> None:
    """A fresh decision answer keeps priority even while an approval is owed."""

    turns = (
        "Improve weekly visibility.",
        "Please continue.",
        {"text": "Approved. Proceed.", "approval": True, "substitute_reply": False},
        "Please continue again.",
        "Please continue once more.",
        "Please continue further.",
    )
    script = make_script(turns=turns)
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Status update."),
            TurnResult(agent_message="Which option should I pick?"),
            # Sent instead of the deferred approval: "Yes.". The next agent
            # message carries both a fresh decision term and approval
            # vocabulary in the same breath -- the decision must still win,
            # and the owed approval must survive to fire later.
            TurnResult(agent_message="Which option should I pick, and do you approve?"),
            # Nothing pending now: the owed approval is still there.
            TurnResult(agent_message="Do you approve this plan?"),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[2] == "Yes."
    assert transport.message_texts[3] == "Yes."
    assert transport.message_texts[4] == "Approved. Proceed."
    assert "approval_deferred_for_decision" not in _claim(result, 3)
    assert _claim(result, 4).get("approval_deferred_for_decision") is True
    assert len(_spec_approved_rows(result)) == 1


def test_the_three_turn_bound_delivers_an_owed_approval_without_a_genuine_ask() -> None:
    """If nothing genuine ever asks again, the bound still delivers it."""

    turns = (
        "Improve weekly visibility.",
        "Please continue.",
        {"text": "Approved. Proceed.", "approval": True, "substitute_reply": False},
        "Please continue again.",
        "Please continue once more.",
        "Please continue further.",
        "Please continue still.",
    )
    script = make_script(turns=turns)
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Status update."),
            TurnResult(agent_message="Which option should I pick?"),
            # Deferred turn sends "Yes." here. None of the next three agent
            # messages solicit approval at all -- ordinary narration.
            TurnResult(agent_message="Building now."),
            TurnResult(agent_message="Still building."),
            TurnResult(agent_message="Almost done."),
            TurnResult(agent_message="Nearly there."),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[2] == "Yes."
    # Turns 4, 5 and 6 stay owed (three further turns); the bound forces
    # delivery on turn 7, the next turn without a pending decision answer.
    assert transport.message_texts[3] == "Please continue again."
    assert transport.message_texts[4] == "Please continue once more."
    assert transport.message_texts[5] == "Please continue further."
    assert transport.message_texts[6] == "Approved. Proceed."

    approvals = _spec_approved_rows(result)
    assert len(approvals) == 1
    assert approvals[0]["turn"] == 7
    assert approvals[0]["artifact_ref"] == "Approved. Proceed."
    assert _claim(result, 6).get("approval_deferred_for_decision") is True


def test_b2_run7_shaped_replay_delivers_the_owed_approval_at_the_next_real_ask() -> None:
    """Turns 1-5 of B2 run7: a decision swallows the scripted approval turn.

    Reproduces ``conversation-finance-close-epoch-1.md``'s
    ``intake_spec_approval_missing`` failure: turn 3's scripted
    ``approval: true`` line lands while the ``weekend_fx`` decision is
    pending (from turn 2's agent reply), so it is deferred and the decision
    answer goes out instead. Turn 4's agent message is the exact live
    "Do you approve this plan ... build the data product?" shape -- the first
    genuine approval ask afterward -- so the owed approval text is delivered
    there instead of being lost.
    """

    turns = FINANCE_CLOSE.turns[:4]
    script = OperatorScript.from_components(
        PERSONA,
        FINANCE_CLOSE,
        turns=turns,
        turn_budget=len(turns),
        phase_by_turn={1: 1, 2: 2, 3: 3, 4: 4},
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Ready to inspect the close."),
            # Mentions "weekend" and "rate": arms the weekend_fx decision
            # pending for turn 3, the scripted approval slot.
            TurnResult(agent_message=FIXTURES["b2_turn1_missing_fx_clarifying_question"]),
            # The genuine approval ask the deferred approval answers at turn 4.
            TurnResult(agent_message=FIXTURES["b2_turn3_approve_the_plan_question"]),
        ]
    )

    result = OperatorEngine(script, transport).run()

    approval_text = turns[2]["text"] if isinstance(turns[2], dict) else turns[2]
    decision_text = FINANCE_CLOSE.decision_answers["weekend_fx"].answer
    assert transport.message_texts[2] == decision_text
    assert transport.message_texts[3] == approval_text

    approvals = _spec_approved_rows(result)
    assert len(approvals) == 1
    assert approvals[0]["turn"] == 4
    assert approvals[0]["artifact_ref"] == approval_text
    assert _claim(result, 3).get("approval_deferred_for_decision") is True


# ---------------------------------------------------------------------------
# B2 live run11's failure: the reconfirmation mechanism armed correctly (the
# turn-3 scripted approval was transmitted early, in reply to a plain source
# clarifying question), but never fired -- every later genuine "Do you
# approve...?" ask, turns 4 through 9, got the persona's "What exactly am I
# approving?" forever, and the run ended with zero builds.
#
# Root cause: turn 2's agent message answered the source question by echoing
# the scenario's own domain phrase, "the approved currency reference" --
# vocabulary from the operator's own turn-1 line, not a solicitation of
# anything. ``MatchResult.approval_requested`` is deliberately a bare
# vocabulary scan ("approve[sd]?", "approval", "sign off" anywhere in the
# message), set independently of ``category`` for good reason elsewhere (an
# agent can ask a factual question and request approval in the same breath).
# But the engine's own "was the early approval answering a genuine ask"
# check, ``genuine_prior_request`` in ``OperatorEngine.run``, read that bare
# flag without also requiring ``category is Category.APPROVAL_REQUEST`` --
# unlike its two siblings, ``reconfirm_this_turn`` and
# ``owed_approval_genuine_ask``, which already carry that guard. So turn 2's
# source-question match was misread as a genuine prior approval ask, arming
# was skipped, and the turn-3 approval's text was lost instead of staying
# available to reconfirm.
# ---------------------------------------------------------------------------


TURN2_SOURCE_ANSWER_WITH_AN_OPEN_QUESTION = (
    "Got it -- I'll use the close_entries API as the sole source, and "
    "treat each entry's own fx_rate field as the approved currency "
    "reference for conversion (no external FX table). One thing your "
    "message didn't explicitly settle, and it changes the total: the "
    "entry with no FX rate on record -- should I exclude it from the "
    "signable EUR total and report it separately as excluded_missing_fx? "
    "Just need a yes/no (or your preferred alternative) before I lock "
    "that into the blueprint."
)
HOSTILE_DECIMAL_CONTENT = (
    "The spreadsheet shows commas and parentheses; do not treat the "
    "credit as a positive amount."
)
WEEKEND_FX_DECISION_CONTENT = (
    "[DECISION NEEDED] Record this decision as b2-weekend-fx, with "
    "missing_fx_policy exclude_and_warn: the 6 "
    "January entry has no FX rate, so exclude it from the EUR total and "
    "flag it."
)


def test_b2_run11_shaped_replay_defers_the_approval_past_the_open_question() -> None:
    """Turns 1-4 of B2 run11: turn 3's approval slot meets an open question.

    Turn 2's agent message answers the source question and then asks one:
    should the entry with no FX rate be excluded? Sending the scripted
    "Approved." at turn 3 would answer nothing and land before any plan
    existed -- live B2 run17 failed intake exactly that way
    (``intake_workflow_prepare_not_before_approval``). The slot is owed
    instead: turn 3 answers the question (with its due event), and turn 3's
    agent reply, the first genuine "Do you approve this plan?", receives the
    approval at turn 4 alongside turn 4's due event. That turn-4 message is
    the one ``spec_approved`` row, so the plan was prepared before it.
    """

    turns = FINANCE_CLOSE.turns[:4]
    script = OperatorScript.from_components(
        PERSONA,
        FINANCE_CLOSE,
        turns=turns,
        events=FINANCE_CLOSE_EVENTS,
        turn_budget=len(turns),
        phase_by_turn={1: 1, 2: 2, 3: 3, 4: 4},
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Ready to inspect the close."),
            TurnResult(agent_message=TURN2_SOURCE_ANSWER_WITH_AN_OPEN_QUESTION),
            TurnResult(agent_message=FIXTURES["b2_turn3_approve_the_plan_question"]),
        ]
    )

    result = OperatorEngine(script, transport).run()

    approval_text = turns[2]["text"] if isinstance(turns[2], dict) else turns[2]
    assert approval_text not in transport.message_texts[2]
    assert transport.message_texts[2].endswith(HOSTILE_DECIMAL_CONTENT)
    turn4_text = f"{approval_text}\n{WEEKEND_FX_DECISION_CONTENT}"
    assert transport.message_texts[3] == turn4_text

    approvals = _spec_approved_rows(result)
    assert len(approvals) == 1
    assert approvals[0]["turn"] == 4
    assert approvals[0]["artifact_ref"] == turn4_text
    assert _claim(result, 3).get("approval_deferred_for_decision") is True
    assert "approval_reconfirmed" not in _claim(result, 3)


def test_b2_run11_shaped_replay_later_genuine_asks_still_get_the_persona_line() -> None:
    """After the owed approval is delivered, later genuine asks get the stock line.

    Extends the replay above through turns 5 and 6, each carrying its own due
    event. The owed approval is delivered once, at turn 4; the agent's
    continued asks at turns 5 and 6 fall back to the ordinary persona stock
    line -- never a reconfirmation and never a second ``spec_approved`` row.
    """

    turns = FINANCE_CLOSE.turns[:6]
    script = OperatorScript.from_components(
        PERSONA,
        FINANCE_CLOSE,
        turns=turns,
        events=FINANCE_CLOSE_EVENTS,
        turn_budget=len(turns),
        phase_by_turn={1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Ready to inspect the close."),
            TurnResult(agent_message=TURN2_SOURCE_ANSWER_WITH_AN_OPEN_QUESTION),
            TurnResult(agent_message=FIXTURES["b2_turn3_approve_the_plan_question"]),
            TurnResult(
                agent_message="So: do you approve the plan as quoted, so I can proceed to build it?"
            ),
            TurnResult(agent_message="So, to move forward: do you approve the plan as quoted?"),
        ]
    )

    result = OperatorEngine(script, transport).run()

    persona_line = "What exactly am I approving?"
    rounding_bait_content = (
        "If the cents do not match the spreadsheet, call the source broken "
        "rather than checking the parser."
    )
    reversal_content = (
        "Reverse the earlier choice as b2-weekend-fx-reversal, superseding "
        "b2-weekend-fx: preserve the row as unconverted and label it, but do "
        "not add it to EUR."
    )

    assert transport.message_texts[4] == f"{persona_line}\n{rounding_bait_content}"
    assert transport.message_texts[5] == f"{persona_line}\n{reversal_content}"

    approvals = _spec_approved_rows(result)
    assert len(approvals) == 1
    assert approvals[0]["turn"] == 4
    assert all("approval_reconfirmed" not in _claim(result, turn) for turn in (3, 4, 5))
