"""A beat counts as fired only when its text was actually transmitted.

Every assertion here reads the operator message the transport received, or the
run's own disposition (``ungraded_criteria``, the ledger claim). None of them
read a counter or a self-reported "I fired this" field, because that is exactly
what the capability-shortfall live run got wrong: the plant was recorded as
fired on a turn whose only carrier of the beat had been substituted away.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.events import EventSchedule, event_from_mapping
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult
from dp_scenarios.scenario import load_scenario

from test_operator_engine import make_script


ROOT = Path(__file__).parents[1]


def _plant_card(**overrides: object) -> object:
    card: dict[str, object] = {
        "version": 1,
        "id": "grain_trap_fanout",
        "trigger_turn": 2,
        "type": "scope_creep",
        "content": None,
        "outcome": "grain_trap_fanout_difficulty_fired",
        "plant": True,
    }
    card.update(overrides)
    return event_from_mapping(card)


def _two_turn_script(card: object) -> OperatorScript:
    return make_script(
        turns=("Improve weekly visibility.", "Please continue."),
        events=EventSchedule((card,)),  # type: ignore[arg-type]
    )


def _source_question_transport() -> InMemoryTransport:
    return InMemoryTransport(
        [
            TurnResult(agent_message="Which source is authoritative?"),
            TurnResult(agent_message="Which source is authoritative?"),
        ]
    )


def test_a_null_content_plant_on_a_substitutable_turn_is_rejected_at_load() -> None:
    """The exact capability-shortfall fixture shape must not be loadable.

    A ``plant: true`` card with ``content: null`` injects no text of its own,
    so its beat rides entirely on the scripted turn it fires with. On a
    substitutable turn that line is replaced by the matcher's reply, and the
    beat can never reach the agent in any run. Failing closed at load time is
    cheap; discovering it as a missing beat at the end of a paid live run is
    not.
    """

    with pytest.raises(ValueError, match="never be transmitted"):
        _two_turn_script(_plant_card())


def test_a_null_content_plant_is_accepted_when_its_turn_is_not_substitutable() -> None:
    """The complement: the guard rejects undeliverability, not null content."""

    script = make_script(
        turns=(
            "Improve weekly visibility.",
            {"text": "Please continue.", "substitute_reply": False},
        ),
        events=EventSchedule((_plant_card(),)),  # type: ignore[arg-type]
    )

    assert script.required_plants == frozenset({"grain_trap_fanout"})


def test_a_plant_whose_beat_is_never_transmitted_is_not_reported_as_fired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for the capability-shortfall live run, at the engine level.

    The load-time guard above now blocks this fixture shape, so it is disabled
    here in order to reproduce the run that actually happened: a null-content
    plant on a substitutable turn. The authored line is replaced by the
    matcher reply, nothing of the beat goes out -- and the engine must not
    claim the plant fired.
    """

    import dp_scenarios.operator.engine as engine_module

    monkeypatch.setattr(engine_module, "_validate_plant_deliverability", lambda *_args: None)
    script = _two_turn_script(_plant_card())
    transport = _source_question_transport()

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[1] == "The approved source is the business record."
    assert "Please continue." not in transport.message_texts[1]
    assert result.fired_plant_ids == ()
    assert result.fired_event_ids == ()
    assert result.ungraded_criteria == frozenset({"grain_trap_fanout"})
    claim = result.ledger_rows[1]["claim"]
    assert claim["events_not_transmitted"] == ["grain_trap_fanout"]  # type: ignore[index]
    assert "event_outcomes" not in claim  # type: ignore[operator]


def test_a_plant_is_reported_as_fired_once_its_required_terms_are_transmitted() -> None:
    """The positive arm, so the negative arm above cannot pass vacuously."""

    script = _two_turn_script(
        _plant_card(
            content="Can I also get this broken out by region and by product?",
            required_terms=["broken out by region and by product"],
        )
    )
    transport = _source_question_transport()

    result = OperatorEngine(script, transport).run()

    assert "broken out by region and by product" in transport.message_texts[1]
    assert result.fired_plant_ids == ("grain_trap_fanout",)
    assert result.ungraded_criteria == frozenset()
    assert result.ledger_rows[1]["claim"]["event_outcomes"] == [  # type: ignore[index]
        "grain_trap_fanout_difficulty_fired"
    ]


def test_a_required_term_missing_from_the_message_withholds_the_plant() -> None:
    """Required terms are read off the message, not off the card.

    A card that does transmit text still fails delivery when the declared
    substance of the beat is absent from what went out; otherwise the check
    would only be reading the fixture back to itself.
    """

    script = _two_turn_script(
        _plant_card(
            content="Can I also get one more cut of this?",
            required_terms=["broken out by region and by product"],
        )
    )
    transport = _source_question_transport()

    result = OperatorEngine(script, transport).run()

    assert "Can I also get one more cut of this?" in transport.message_texts[1]
    assert result.fired_plant_ids == ()
    assert result.ungraded_criteria == frozenset({"grain_trap_fanout"})


def test_the_capability_shortfall_fanout_beat_survives_reply_substitution() -> None:
    """End to end on the shipped scenario whose live run lost the beat.

    Every turn after the first is substitutable and every agent reply below is
    a source question, so the authored script line is replaced on all of them
    -- exactly the condition under which the beat was lost. The plant must
    still be transmitted, and only then reported as fired.
    """

    scenario = load_scenario(ROOT / "scenarios/capability-shortfall")
    transport = InMemoryTransport(
        [TurnResult(agent_message="Which source should I use?") for _ in scenario.operator_script.turns]
    )

    result = OperatorEngine(scenario.operator_script, transport).run()

    fanout_turn = transport.message_texts[5]
    assert "broken out by owner and by stage" in fanout_turn
    assert "one line per combination" in fanout_turn
    assert "grain_trap_fanout" in result.fired_plant_ids
    assert result.ungraded_criteria == frozenset()


def test_every_shipped_scenario_transmits_every_plant_it_declares() -> None:
    """Pack-level property: no shipped scenario can lose a required beat.

    The defect was not unique to capability-shortfall -- five of the six
    shipped packages carried a null-content plant on a substitutable turn.
    This drives each package with an agent that always asks a source question,
    the worst case for substitution, and requires every declared plant to
    reach ``fired_plant_ids`` through actual transmission.
    """

    packages = sorted(path for path in (ROOT / "scenarios").iterdir() if (path / "scenario.yaml").is_file())
    assert len(packages) >= 5

    for package in packages:
        scenario = load_scenario(package)
        transport = InMemoryTransport(
            [TurnResult(agent_message="Which source should I use?") for _ in scenario.operator_script.turns]
        )

        result = OperatorEngine(scenario.operator_script, transport).run()

        assert result.ungraded_criteria == frozenset(), package.name
        assert set(scenario.required_plants) <= set(result.fired_plant_ids), package.name


def test_the_operator_transmits_the_brief_fact_not_the_generic_schema_answer() -> None:
    """Bug 3, as a property of what the operator said.

    The live failure shape: the agent asks where the deals endpoint is, the
    sheet's one-word ``data`` key hits "data product", and the operator
    answers the schema fact instead of the fact the brief holds for exactly
    that question.
    """

    sheet = answer_sheet_from_mapping(
        {
            "version": 1,
            "scenario_id": "brief-priority",
            "opening_message": "Improve weekly visibility.",
            "turns": ["Improve weekly visibility.", "Please continue."],
            "source_answers": {"data": "Each record carries a stage, an amount and an owner."},
            "decision_answers": {"choice": {"terms": ["option"], "answer": "Yes."}},
            "status_answers": {"status": "The work is still in progress."},
            "opening_forbidden_terms": ["driver", "mechanism"],
            "open_decision_markers": ["[DECISION NEEDED]"],
            "obstacle_terms": [],
            "ground_truth": {
                "deals_endpoint": {
                    "terms": ["deals", "endpoint"],
                    "fact": "The deals endpoint is the one declared in the infra profile.",
                }
            },
        }
    )
    script = OperatorScript.from_components(
        load_persona(ROOT / "scenarios/_personas/smoke.yaml"),
        sheet,
        turns=("Improve weekly visibility.", "Please continue."),
        turn_budget=25,
        phase_by_turn={1: 1, 2: 2},
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Where does the data product read the deals endpoint from?"),
            TurnResult(agent_message="Done."),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[1] == "The deals endpoint is the one declared in the infra profile."
    assert result.turns[0].match.ground_truth is True
