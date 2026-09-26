"""Regression tests for the "owed approval" reconfirmation mechanism.

B2's live run6 transmitted its scripted ``approval: true`` turn while the
agent's previous message was only a clarifying question -- nothing had
actually been asked for approval yet. Every later genuine "Do you approve
...?" ask then misrouted (see the matcher fixes in
``test_operator_matcher_b2b5_regressions.py``), and even once routing was
fixed, the operator's canned "What exactly am I approving?" persona line
demanded specifics the agent had already supplied, over and over.

Unconditional transmission of the scripted approval at its declared slot is
kept exactly as it was (see ``test_operator_engine_driver.py`` and
``test_scenario_capability_shortfall.py``, which are regression suites for
that exact property and are not touched here). What is added is narrower: the
engine remembers the text it transmitted early, and the first time afterward
that the agent genuinely asks for approval, it reconfirms that same text
verbatim instead of running the ordinary matcher/persona path. This never
mints a second ``spec_approved`` row and fires at most once per run.
"""

from __future__ import annotations

import json
from pathlib import Path

from dp_scenarios.operator.answer_sheet import load_answer_sheet
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
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
            # The clarifying question before the scripted approval turn: no
            # approval was actually asked for yet.
            TurnResult(agent_message="What exactly do you need from me before I continue?"),
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
            TurnResult(agent_message="What exactly do you need from me before I continue?"),
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
