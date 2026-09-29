"""Staged decision answers unlock only after their event is delivered."""

from __future__ import annotations

from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping, load_answer_sheet
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript, operator_script_hash
from dp_scenarios.operator.events import EventSchedule, event_from_mapping
from dp_scenarios.operator.driver import DriverOperator, DriverView
from dp_scenarios.operator.matcher import MatcherBank
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult


ROOT = Path(__file__).parents[1]
PERSONA = load_persona(ROOT / "scenarios/_personas/smoke.yaml")
OPENING = "I want an MRR bridge for every month."
INITIAL_ID = "same_month_classification"
REVISED_ID = "same_month_classification_revised"
INITIAL_ANSWER = "At first, show the two directions separately."
REVISED_ANSWER = "Use prior-month close and current-month close so interim movements net out."
DECISION_TERMS = ("within the same month", "both directions")
DECISION_SYNONYMS = {
    "within the same month": ["in the same month", "inside the same month", "within one month"],
    "both directions": [
        "down then up",
        "dropped then went back up",
        "decreased and increased",
        "downgrade and upgrade",
    ],
}


def _sheet(*, staged: bool = True, missing_event: bool = False):
    initial: dict[str, object] = {
        "terms": list(DECISION_TERMS),
        "answer": INITIAL_ANSWER,
        "synonyms": DECISION_SYNONYMS,
    }
    revised: dict[str, object] = {
        "terms": list(DECISION_TERMS),
        "answer": REVISED_ANSWER,
        "synonyms": DECISION_SYNONYMS,
    }
    if staged:
        initial["available_after_event"] = "missing-event" if missing_event else "B7-same-month"
        revised["available_after_event"] = "E8"
    return answer_sheet_from_mapping(
        {
            "version": 1,
            "scenario_id": "b7-staged-answers-test",
            "opening_message": OPENING,
            "turns": [OPENING, "Please continue.", "Please continue again.", "Please wrap up."],
            "source_answers": {"source": "The event file is the source."},
            "decision_answers": {INITIAL_ID: initial, REVISED_ID: revised},
            "status_answers": {"status": "The work is still in progress."},
            "opening_forbidden_terms": ["classification", "ruling", "B7-same-month", "E8"],
            "open_decision_markers": ["[DECISION NEEDED]"],
            "obstacle_terms": [],
        }
    )


def _event(card_id: str, trigger_turn: int, content: str):
    return event_from_mapping(
        {
            "version": 1,
            "id": card_id,
            "trigger_turn": trigger_turn,
            "type": "scope_creep" if card_id == "B7-same-month" else "decision_reversal",
            "content": content,
            "outcome": f"{card_id}-delivered",
        }
    )


def _script(sheet, cards=(), *, turn_count: int = 4) -> OperatorScript:
    turns = (OPENING,) + tuple(f"Please continue on turn {turn}." for turn in range(2, turn_count + 1))
    return OperatorScript.from_components(
        PERSONA,
        sheet,
        events=EventSchedule(tuple(cards)),
        turns=turns,
        turn_budget=turn_count,
        phase_by_turn={turn: min(turn, 7) for turn in range(1, turn_count + 1)},
    )


@pytest.mark.parametrize(
    "question",
    [
        "Which approach should show a customer who went down then up within the same month?",
        "Could you decide how to display a customer who dropped then went back up inside the same month?",
        "How should a customer who decreased and increased within one month appear?",
        "How should a downgrade and upgrade in the same month be shown?",
    ],
)
def test_b7_decision_matches_realistic_same_month_synonyms(question: str) -> None:
    match = MatcherBank(PERSONA, _sheet()).reply_for(
        question, available_event_ids=("B7-same-month",)
    )

    assert match.decision_id == INITIAL_ID
    assert match.reply == INITIAL_ANSWER


@pytest.mark.parametrize(
    "question",
    [
        "Should I use the within the same month figure?",
        "How should the down then up case appear?",
    ],
)
def test_same_month_decision_requires_both_concepts(question: str) -> None:
    match = MatcherBank(PERSONA, _sheet()).reply_for(
        question, available_event_ids=("B7-same-month",)
    )

    assert match.decision_id is None
    assert match.reply not in {INITIAL_ANSWER, REVISED_ANSWER}


def test_legacy_mapping_and_script_hash_are_unchanged_without_staging() -> None:
    sheet = _sheet(staged=False)
    mapping = sheet.to_mapping()

    assert mapping["decision_answers"][INITIAL_ID] == {
        "terms": list(DECISION_TERMS),
        "answer": INITIAL_ANSWER,
        "synonyms": DECISION_SYNONYMS,
    }
    script = _script(sheet)
    assert operator_script_hash(script) == "096f1154659dc8b58a31e0177c320a99413ab72ef2297ea6b24a2a84d73a78d9"
    cards = (
        _event("B7-same-month", 2, "Please tell me how you want that represented."),
        _event("E8", 3, "Please revise the classification."),
    )
    assert operator_script_hash(_script(_sheet(), cards)) != operator_script_hash(
        _script(sheet, cards)
    )


def test_existing_finance_sheet_keeps_its_legacy_reply_and_hash_shape() -> None:
    sheet = load_answer_sheet(ROOT / "scenarios/finance-close/answer-sheet.yaml")
    decision = sheet.decision_answers["weekend_fx"]
    script = OperatorScript.from_components(
        PERSONA,
        sheet,
        turns=(sheet.opening_message, "Please continue."),
        turn_budget=2,
        phase_by_turn={1: 1, 2: 2},
    )

    assert decision.available_after_event is None
    assert "available_after_event" not in sheet.to_mapping()["decision_answers"]["weekend_fx"]
    assert MatcherBank(PERSONA, sheet).reply_for("Should we exclude the weekend rate?").reply == decision.answer
    assert operator_script_hash(script) == "4d186437b94f671b02c18d3641de36192e6b55169af30c452efaac387dd68ceb"


def test_a_staged_answer_requires_a_declared_event_id() -> None:
    with pytest.raises(ValueError, match="undeclared event id.*missing-event"):
        _script(_sheet(missing_event=True))


def test_initial_and_revised_answers_unlock_only_after_transmitted_events() -> None:
    initial_event_text = "One customer went down and then up within a month. How should that appear?"
    revised_event_text = "I am changing that ruling. Please revise it for prior-month and current-month close."
    script = _script(
        _sheet(),
        (
            _event("B7-same-month", 2, initial_event_text),
            _event("E8", 3, revised_event_text),
        ),
    )
    question = "How should a customer who went down then up within the same month appear?"
    transport = InMemoryTransport(
        [
            TurnResult(agent_message=question),
            TurnResult(agent_message=question),
            TurnResult(agent_message=question),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert result.turns[0].match.decision_id is None
    assert result.turns[1].match.decision_id == INITIAL_ID
    assert result.turns[1].delivered_decision_id is None
    assert result.turns[2].match.decision_id == REVISED_ID
    assert result.turns[2].delivered_decision_id == INITIAL_ID
    assert result.turns[3].delivered_decision_id == REVISED_ID
    assert result.fired_event_ids == ("B7-same-month", "E8")

    outgoing = transport.message_texts
    assert INITIAL_ANSWER not in outgoing[0]
    assert REVISED_ANSWER not in outgoing[0]
    assert INITIAL_ID not in outgoing[0]
    assert REVISED_ID not in outgoing[0]
    assert "B7-same-month" not in outgoing[0]
    assert "E8" not in outgoing[0]
    assert INITIAL_ANSWER not in outgoing[1]
    assert REVISED_ANSWER not in outgoing[1]
    assert INITIAL_ID not in outgoing[1]
    assert REVISED_ID not in outgoing[1]
    assert "B7-same-month" not in outgoing[1]
    assert INITIAL_ANSWER in outgoing[2]
    assert REVISED_ANSWER not in outgoing[2]
    assert INITIAL_ID not in outgoing[2]
    assert REVISED_ID not in outgoing[2]
    assert "E8" not in outgoing[2]
    assert REVISED_ANSWER in outgoing[3]
    assert INITIAL_ID not in outgoing[3]
    assert REVISED_ID not in outgoing[3]
    assert "B7-same-month" not in "\n".join(outgoing)
    assert "E8" not in "\n".join(outgoing)


def test_early_driver_view_has_no_staged_answer_or_gate_id() -> None:
    sheet_mapping = _sheet().to_mapping()
    sheet_mapping["driver_forbidden_terms"] = ["net"]
    sheet = answer_sheet_from_mapping(sheet_mapping)
    script = _script(
        sheet,
        (
            _event("B7-same-month", 3, "One customer moved in both directions."),
            _event("E8", 4, "Please revise the decision."),
        ),
        turn_count=3,
    )
    views: list[DriverView] = []

    def author(view: DriverView) -> str:
        views.append(view)
        return "Please keep going with the requested bridge."

    question = "How should a customer who went down then up within the same month appear?"
    transport = InMemoryTransport(
        [TurnResult(agent_message=question), TurnResult(agent_message=question), TurnResult(agent_message="Done.")]
    )

    OperatorEngine(
        script,
        transport,
        driver=DriverOperator(author, model_id="test-driver", temperature=0.0),
    ).run()

    early_view = views[0]
    view_text = str(early_view.to_mapping())
    assert early_view.selected_reply == ""
    assert early_view.beat is None
    for hidden_value in (INITIAL_ID, REVISED_ID, "B7-same-month", "E8", INITIAL_ANSWER, REVISED_ANSWER):
        assert hidden_value not in view_text


def test_event_that_fails_message_delivery_does_not_unlock_its_answer() -> None:
    undelivered = event_from_mapping(
        {
            "version": 1,
            "id": "B7-same-month",
            "trigger_turn": 2,
            "type": "scope_creep",
            "content": "I need to ask you about one customer.",
            "required_terms": ["phrase that is never delivered"],
            "outcome": "initial-question-delivered",
        }
    )
    delayed_revision = event_from_mapping(
        {
            "version": 1,
            "id": "E8",
            "trigger_turn": 3,
            "type": "decision_reversal",
            "content": "Please revise the classification.",
            "required_terms": ["another phrase that is never delivered"],
            "outcome": "revised-question-delivered",
        }
    )
    script = _script(_sheet(), (undelivered, delayed_revision), turn_count=3)
    question = "How should a customer who went down then up within the same month appear?"
    transport = InMemoryTransport(
        [TurnResult(agent_message=question), TurnResult(agent_message=question), TurnResult(agent_message="Done.")]
    )

    result = OperatorEngine(script, transport).run()

    assert result.fired_event_ids == ()
    assert result.turns[1].match.decision_id is None
    assert INITIAL_ANSWER not in "\n".join(transport.message_texts)
    assert REVISED_ANSWER not in "\n".join(transport.message_texts)


def test_selected_but_not_yet_sent_answer_has_no_delivery_id() -> None:
    script = _script(
        _sheet(),
        (
            _event("B7-same-month", 2, "Please tell me how you want that represented."),
            _event("E8", 3, "Please revise the classification."),
        ),
        turn_count=2,
    )
    question = "How should a customer who went down then up within the same month appear?"
    transport = InMemoryTransport([TurnResult(agent_message="Continue."), TurnResult(agent_message=question)])

    result = OperatorEngine(script, transport).run()

    selected = result.turns[-1]
    assert selected.match.decision_id == INITIAL_ID
    assert selected.delivered_decision_id is None
    assert INITIAL_ANSWER not in transport.message_texts[-1]
