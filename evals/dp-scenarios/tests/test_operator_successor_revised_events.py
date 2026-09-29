"""A revised release may be a successor workflow the operator authorized (r416)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.events import (
    EventSchedule,
    event_from_mapping,
    successor_authorization_turn,
)
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult
from dp_scenarios.scenario import load_scenario

ROOT = Path(__file__).parents[1]
SCENARIO = load_scenario(ROOT / "scenarios/mrr-waterfall")
CARDS = {card.card_id: card for card in SCENARIO.events.cards}

ASK = (
    "I haven't revised anything. A published workflow can't be revised in "
    "place, so this would be a new versioned product under a new workflow id."
)


def _snapshot(*, successor: bool) -> dict[str, object]:
    runs = [
        ("mrr-waterfall", "run-1", "definition-a", 12),
        ("mrr-waterfall-v2" if successor else "mrr-waterfall", "run-2", "definition-b", 33),
    ]
    return {
        "run_records": {
            "schema": "dp-scenario-run-records-v1",
            "runs": [
                {"workflow_id": w, "run_id": r, "definition_id": d, "status_history": [{"turn": t, "status": "Published"}]}
                for w, r, d, t in runs
            ],
        },
        "publication_history": {
            "schema": "dp-scenario-publication-history-v1",
            "releases": [{"workflow_id": w, "run_id": r, "definition_id": d} for w, r, d, _ in runs],
        },
    }


def _texts(*, asked: bool = True) -> tuple[tuple[int, str, str], ...]:
    return (
        (30, ASK if asked else "Nothing to revise.", "I'm changing that same-month decision."),
        (31, "I'll stop here.", "I don't know, you tell me."),
        (32, "Prepared.", "Please continue with the revised definition."),
        (33, "Built and published.", "Approved."),
    )


def _fire(snapshot: dict[str, object], texts: object, *, turn: int = 40) -> tuple[str, ...]:
    injections = SCENARIO.events.fire(
        turn,
        run_records=snapshot["run_records"],
        publication_history=snapshot["publication_history"],
        delivered_event_turns={
            "B7-same-month": 4, "B7-spreadsheet-challenge": 14,
            "B7-billing-contact-request": 15, "B7-E8": 30,
        },
        used_event_ids=("B7-same-month", "B7-spreadsheet-challenge", "B7-billing-contact-request", "B7-E8"),
        turn_texts=texts,
    )
    return tuple(item.card_id for item in injections)


def test_same_workflow_revision_still_releases_e3_without_any_transcript() -> None:
    assert _fire(_snapshot(successor=False), None, turn=47) == ("B7-E3",)


def test_authorized_successor_workflow_releases_e3() -> None:
    assert _fire(_snapshot(successor=True), _texts(), turn=47) == ("B7-E3",)


def test_successor_workflow_without_an_agent_ask_does_not_release_e3() -> None:
    assert _fire(_snapshot(successor=True), _texts(asked=False), turn=47) == ()
    assert _fire(_snapshot(successor=True), None, turn=47) == ()


def test_successor_authorization_needs_an_operator_reply_after_the_ask() -> None:
    # Asked and prepared on the same turn: no later operator message exists
    # inside the window, so nothing authorized the new product.
    assert successor_authorization_turn(_texts(), after_turn=30, deadline_turn=30) is None
    assert successor_authorization_turn(_texts(), after_turn=30, deadline_turn=31) == 31
    # An ask that predates the reversal does not count.
    assert successor_authorization_turn(_texts(), after_turn=31, deadline_turn=33) is None


def _stub(card_id: str, turn: int, **extra: object) -> object:
    return event_from_mapping({
        "version": 1, "id": card_id, "trigger_turn": turn, "type": "decision_reversal",
        "content": "Ruling.", "outcome": f"{card_id}_done", **extra,
    })


def test_e8_card_declares_and_engine_records_the_decision_it_delivers() -> None:
    assert CARDS["B7-E8"].delivers_decision == "same_month_classification_revised"
    card = event_from_mapping({
        "version": 1, "id": "B7-E8", "trigger_turn": 2, "type": "decision_reversal",
        "content": CARDS["B7-E8"].content, "outcome": "ruling_stated",
        "delivers_decision": "same_month_classification_revised",
    })
    script = OperatorScript.from_components(
        SCENARIO.persona, SCENARIO.answer_sheet,
        # The answer sheet's staged decisions name both events.
        events=EventSchedule((card, _stub("B7-same-month", 3))),
        turns=(SCENARIO.answer_sheet.opening_message, "Please continue.", "Please continue."),
        turn_budget=3, phase_by_turn={1: 1, 2: 1, 3: 1},
    )
    result = OperatorEngine(
        script, InMemoryTransport([TurnResult(agent_message="Working.") for _ in range(3)]),
    ).run()
    assert result.turns[1].event_ids == ("B7-E8",)
    assert result.turns[1].delivered_decision_id == "same_month_classification_revised"
    assert result.turns[0].delivered_decision_id is None
    assert result.turns[2].delivered_decision_id is None


def test_delivers_decision_must_name_a_declared_decision() -> None:
    cards = (
        _stub("B7-E8", 2, delivers_decision="not_declared"),
        _stub("B7-same-month", 3),
    )
    with pytest.raises(ValueError, match="undeclared decision"):
        OperatorScript.from_components(
            SCENARIO.persona, SCENARIO.answer_sheet, events=EventSchedule(cards),
            turns=(SCENARIO.answer_sheet.opening_message, "Please continue.", "Please continue."),
            turn_budget=3, phase_by_turn={1: 1, 2: 1, 3: 1},
        )
