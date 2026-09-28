"""An answerable decision takes one turn; displaced fixed beats retain order.

The script's operator-turn budget is unchanged. If no later slot can carry an
owed beat, the run remains incomplete. A fresh unanswered final question keeps
the more specific ``turn_budget_exhausted_pending_answer`` terminal state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import load_answer_sheet
from dp_scenarios.operator.driver import DriverOperator
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript, TerminalState
from dp_scenarios.operator.events import EventSchedule, event_from_mapping
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult

from test_operator_engine import make_script
from test_operator_engine_driver import make_script as make_driver_script

ROOT = Path(__file__).parents[1]


def completed(message: str) -> TurnResult:
    return TurnResult(
        agent_message=message,
        terminal_result_count=1,
        terminal_result_subtype="success",
        terminal_result_is_error=False,
    )


def test_fixed_beats_and_beat_bound_plant_wait_in_order_after_decision() -> None:
    content_event = event_from_mapping(
        {
            "version": 1,
            "id": "a_current_event",
            "trigger_turn": 2,
            "type": "scope_creep",
            "content": "The source label changed.",
            "outcome": "current_event_fired",
            "plant": True,
        }
    )
    beat_bound_event = event_from_mapping(
        {
            "version": 1,
            "id": "b_beat_bound_event",
            "trigger_turn": 2,
            "type": "scope_creep",
            "content": None,
            "outcome": "beat_bound_event_fired",
            "plant": True,
        }
    )
    script = make_script(
        turns=(
            "Improve weekly visibility.",
            {"text": "Inspect the supplied material.", "substitute_reply": False},
            {"text": "Report the weekly result.", "substitute_reply": False},
            "Please continue.",
        ),
        turn_budget=4,
        events=EventSchedule((content_event, beat_bound_event)),
    )
    transport = InMemoryTransport(
        [
            completed("Which option should I use?"),
            completed("I will use that option."),
            completed("Working on the report."),
            completed("The result is ready."),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts == (
        "Improve weekly visibility.",
        "Yes.\nThe source label changed.",
        "Inspect the supplied material.",
        "Report the weekly result.",
    )
    assert result.fired_plant_ids == ("a_current_event", "b_beat_bound_event")
    assert result.ungraded_criteria == frozenset()
    assert result.terminal_state is TerminalState.COMPLETED


def test_a_dynamic_reapproval_does_not_consume_an_owed_fixed_beat() -> None:
    sheet = load_answer_sheet(ROOT / "scenarios/inventory-position/answer-sheet.yaml")
    persona = load_persona(ROOT / "scenarios/_personas/confidently-wrong.yaml")
    fixed = "Inspect the approved source."
    script = OperatorScript.from_components(
        persona,
        sheet,
        turns=(
            sheet.opening_message,
            {"text": fixed, "substitute_reply": False},
            "Please continue.",
            "Please continue again.",
        ),
        turn_budget=4,
        phase_by_turn={1: 1, 2: 3, 3: 3, 4: 4},
    )
    transport = InMemoryTransport(
        [
            completed("The reviewer found a missing summary. Do you authorize adding the missing summary to the output?"),
            completed("The revised plan is ready. Do you approve this revised plan?"),
            completed("Working on the revised plan."),
            completed("The result is ready."),
        ]
    )

    OperatorEngine(script, transport).run()

    assert transport.message_texts[1] == sheet.decision_answers["review_fix_authorization"].answer
    assert transport.message_texts[2] == sheet.reapproval.answer
    assert transport.message_texts[3] == fixed


def test_review_repair_fixed_beat_waits_for_finding_and_coalesces_with_answer() -> None:
    sheet = load_answer_sheet(ROOT / "scenarios/marketing-attribution/answer-sheet.yaml")
    persona = load_persona(ROOT / "scenarios/_personas/micromanager.yaml")
    repair = sheet.decision_answers["review_fix_authorization"].answer
    script = OperatorScript.from_components(
        persona,
        sheet,
        turns=(sheet.opening_message, {"text": repair, "substitute_reply": False}, "Please continue."),
        turn_budget=3,
        phase_by_turn={1: 1, 2: 7, 3: 7},
    )
    transport = InMemoryTransport(
        [
            completed("Which supplied source should I use?"),
            completed("The independent review found a missing summary. Do you authorize adding it?"),
            completed("I will apply the authorized review correction."),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[1] != repair
    assert transport.message_texts[2] == repair
    assert transport.message_texts.count(repair) == 1
    assert result.terminal_state is TerminalState.COMPLETED


def test_deferred_fixed_beats_leave_a_flexible_slot_for_the_driver() -> None:
    fixed_one = "Inspect the supplied material."
    fixed_two = "Report the weekly result."
    script = make_driver_script(
        turns=(
            "Improve weekly visibility.",
            {"text": fixed_one, "substitute_reply": False},
            {"text": fixed_two, "substitute_reply": False},
            "Please continue.",
            "Please continue again.",
        ),
    )
    transport = InMemoryTransport(
        [
            completed("Which choice should I use?"),
            completed("I will use that option."),
            completed("Working on the report."),
            completed("Continuing the report."),
            completed("The result is ready."),
        ]
    )
    driver = DriverOperator(lambda _view: "Understood, carry on.", model_id="test-driver", temperature=0.0)

    result = OperatorEngine(script, transport, driver=driver).run()

    assert transport.message_texts[2] == fixed_one
    assert transport.message_texts[3] == "Understood, carry on."
    assert transport.message_texts[4] == fixed_two
    assert result.turns[3].operator_mode == "driver"
    assert result.terminal_state is TerminalState.COMPLETED


@pytest.mark.parametrize(
    ("last_agent_message", "expected_state"),
    [
        ("The result is ready.", TerminalState.SCRIPT_EXHAUSTED),
        ("Which option should I use for the next step?", TerminalState.TURN_BUDGET_EXHAUSTED_PENDING_ANSWER),
    ],
)
def test_budget_does_not_silently_discard_an_owed_fixed_beat(
    last_agent_message: str, expected_state: TerminalState
) -> None:
    script = make_script(
        turns=(
            "Improve weekly visibility.",
            {"text": "Inspect the supplied material.", "substitute_reply": False},
        ),
        turn_budget=2,
    )
    transport = InMemoryTransport(
        [
            completed("Which option should I use?"),
            completed(last_agent_message),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[1] == "Yes."
    assert result.terminal_state is expected_state
    assert result.stop_reason == expected_state.value
