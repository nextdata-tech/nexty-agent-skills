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
