"""Integration coverage for the guarded free-authoring operator driver."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.operator import (
    DriverBeat,
    DriverOperator,
    DriverView,
    EventSchedule,
    OperatorEngine,
    OperatorScript,
    event_from_mapping,
)
from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping
from dp_scenarios.operator.generated import GeneratedOperator
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult


ROOT = Path(__file__).parents[1]


def make_script(*, turns: tuple[object, ...] | None = None, events: EventSchedule = EventSchedule(())) -> OperatorScript:
    opening = "Improve weekly visibility."
    sheet = answer_sheet_from_mapping(
        {
            "version": 1,
            "scenario_id": "driver-engine-test",
            "opening_message": opening,
            "turns": list(turns or (
                opening,
                {"text": "Please show the source question verbatim.", "substitute_reply": False},
                "Please continue.",
                {"text": "The specification is approved.", "approval": True},
                "Please continue again.",
            )),
            "source_answers": {"source": "The source is the approved business record."},
            "decision_answers": {"choice": {"terms": ["choice"], "answer": "Choose the approved option."}},
            "status_answers": {"status": "The work is still in progress."},
            "opening_forbidden_terms": ["source", "driver", "mechanism"],
            "open_decision_markers": ["[DECISION NEEDED]"],
            "obstacle_terms": [],
            "driver_forbidden_terms": ["grain", "join", "aggregation"],
            "ground_truth": {
                "grain_fact": {
                    "terms": ["grain"],
                    "fact": "The grain is one row per account; FACT-ONLY-MARKER.",
                },
                "join_fact": {"terms": ["join"], "fact": "The join uses account_id."},
            },
        }
    )
    persona = load_persona(ROOT / "scenarios/_personas/smoke.yaml")
    resolved_turns = tuple(turns or sheet.turns)
    return OperatorScript.from_components(
        persona,
        sheet,
        turns=resolved_turns,  # type: ignore[arg-type]
        events=events,
        turn_budget=len(resolved_turns),
        sentinel=b"ACTIVE-SENTINEL",
        phase_by_turn={index: min(index, 7) for index in range(1, len(resolved_turns) + 1)},
    )


def driver(provider: object) -> DriverOperator:
    return DriverOperator(provider, model_id="test-driver", temperature=0.0)  # type: ignore[arg-type]


def test_driver_authors_only_substitutable_turns_and_approval_stays_verbatim() -> None:
    script = make_script()
    seen: list[DriverView] = []

    def provider(view: DriverView) -> str:
        seen.append(view)
        return "Understood, carry on."

    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Which source is authoritative?"),
            TurnResult(agent_message="Status update."),
            TurnResult(agent_message="Approval requested."),
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    result = OperatorEngine(script, transport, driver=driver(provider)).run()

    assert transport.message_texts == (
        "Improve weekly visibility.",
        "Please show the source question verbatim.",
        "Understood, carry on.",
        "The specification is approved.",
        "Understood, carry on.",
    )
    assert [record.operator_mode for record in result.turns] == [
        "scripted", "scripted", "driver", "scripted", "driver"
    ]
    assert [record.driver_skip_reason for record in result.turns[:4]] == [
        "turn_one", "non_substitutable", None, "approval"
    ]
    approval = next(row for row in result.ledger_rows if row["action_kind"] == "spec_approved")
    assert approval["artifact_ref"] == "The specification is approved."
    assert len(seen) == 2


def test_driver_leading_guard_falls_back_on_every_authorable_turn_and_allows_agent_sanction() -> None:
    turns = ("Improve weekly visibility.", "Please continue.", "Please continue again.")
    script = make_script(turns=turns)
    calls = 0

    def leaking(view: DriverView) -> str:
        nonlocal calls
        calls += 1
        return "The grain is obvious; carry on."

    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Status update."),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    result = OperatorEngine(script, transport, driver=driver(leaking)).run()

    # The property first: the leaked sentence never reaches the agent.
    assert transport.message_texts == (
        "Improve weekly visibility.",
        "The source is the approved business record.",
        "The work is still in progress.",
    )
    assert all("grain" not in text for text in transport.message_texts)
    assert calls == 4
    authorable_turns = [record for record in result.turns if record.driver_skip_reason is None]
    assert len(authorable_turns) == 2
    assert sum(record.driver_leading_rejected for record in result.turns) == len(authorable_turns)
    assert result.turns[1].driver_leading_rejected is True
    assert result.turns[2].driver_leading_rejected is True
    assert result.turns[0].driver_leading_rejected is False
    assert result.turns[0].driver_forbidden_terms_in_force == 0
    assert [record.driver_forbidden_terms_in_force for record in authorable_turns] == [3, 3]
    assert result.ledger_rows[1]["claim"]["driver_leading_rejected"] is True
    assert result.ledger_rows[1]["claim"]["operator_mode"] == "driver_fallback"
    assert "driver_leading_rejected" not in (result.ledger_rows[0]["claim"] or {})

    sanctioned = OperatorEngine(
        script,
        InMemoryTransport(
            [
                TurnResult(agent_message="What is the grain?"),
                TurnResult(agent_message="I already know the grain; what is next?"),
                TurnResult(agent_message="Done.", reported=True),
            ]
        ),
        driver=driver(lambda _view: "The grain is already known; carry on."),
    ).run()
    assert sanctioned.turns[1].operator_message.text == "The grain is already known; carry on."
    assert sanctioned.turns[1].driver_leading_rejected is False
    # The agent's own word sanctioned exactly one term; the other two stay in force.
    assert sanctioned.turns[1].driver_forbidden_terms_exempted == 1
    assert sanctioned.turns[1].driver_forbidden_terms_in_force == 2


def test_driver_view_is_relevance_gated_and_redacted() -> None:
    script = make_script()
    views: list[DriverView] = []

    def provider(view: DriverView) -> str:
        views.append(view)
        return "Understood, carry on."

    OperatorEngine(
        script,
        InMemoryTransport(
            [
                TurnResult(agent_message="What is the source?"),
                TurnResult(agent_message="Status update FIXTURE-SECRET."),
                TurnResult(agent_message="Done.", reported=True),
            ]
        ),
        driver=driver(provider),
        extra_sentinels=[b"FIXTURE-SECRET"],
    ).run()

    assert views
    assert views[0].known_facts == ()
    # Four agent messages precede the second authorable turn; the view carries
    # the last two and no more.
    assert len(views) == 2
    assert views[0].prior_agent_messages == ("What is the source?", "Status update <redacted-sentinel>.")
    assert views[1].prior_agent_messages == ("Done.", "")
    assert all(len(view.prior_agent_messages) <= 2 for view in views)
    assert all("FIXTURE-SECRET" not in json.dumps(view.to_mapping()) for view in views)
    assert "FIXTURE-SECRET" not in json.dumps(views[0].to_mapping())
    # No agent message in this run says "grain", so the grain fact's token is
    # owed to no view at all -- not just to the first one.
    assert all("FACT-ONLY-MARKER" not in json.dumps(view.to_mapping()) for view in views)
    assert all(view.known_facts == () for view in views)
    assert all("ACTIVE-SENTINEL" not in json.dumps(view.to_mapping()) for view in views)

    views.clear()
    OperatorEngine(
        script,
        InMemoryTransport(
            [
                TurnResult(agent_message="What is the source?"),
                TurnResult(agent_message="What is the grain?"),
                TurnResult(agent_message="Done.", reported=True),
            ]
        ),
        driver=driver(provider),
    ).run()
    assert views[0].known_facts == (
        ("grain_fact", "The grain is one row per account; FACT-ONLY-MARKER."),
    )
    assert "FACT-ONLY-MARKER" in json.dumps(views[0].to_mapping())
    # known_facts is ground truth only. The decision and status banks are the
    # rubric the run is graded against and must never be offered to a driver.
    sheet = script.answer_sheet
    assert all(key in sheet.ground_truth for key, _ in views[0].known_facts)
    rubric = ("The work is still in progress.", "Choose the approved option.")
    assert all(text not in json.dumps(views[0].known_facts) for text in rubric)


def test_driver_fact_memory_and_beat_recomposition_are_recorded() -> None:
    event = event_from_mapping(
        {
            "version": 1,
            "id": "scope-creep",
            "trigger_turn": 3,
            "type": "scope_creep",
            "content": "Please add the extra scope.",
            "outcome": "scope_creep_fired",
            "required_terms": ["scope", "refusal"],
        }
    )
    script = make_script(
        turns=("Improve weekly visibility.", "Please continue.", "Please continue with scope refusal."),
        events=EventSchedule((event,)),
    )
    views: list[DriverView] = []

    def provider(view: DriverView) -> str:
        views.append(view)
        # Turn 2 leaks a forbidden term on both attempts, so the *scripted*
        # ground-truth answer is what actually reaches the agent; turn 3 keeps
        # missing a mandatory beat term.
        return (
            "Let us discuss the join."
            if view.turn == 2
            else "I will not take on this scope."
        )

    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the grain?"),
            TurnResult(agent_message="What is the grain?"),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    result = OperatorEngine(script, transport, driver=driver(provider)).run()

    assert views[0].known_facts == (
        ("grain_fact", "The grain is one row per account; FACT-ONLY-MARKER."),
    )
    # The fact is remembered as stated because it was *transmitted* on the
    # fallback -- not because a scan found the question's own trigger word in
    # some authored sentence -- and the immediate re-ask is suppressed.
    assert transport.message_texts[1] == "The grain is one row per account; FACT-ONLY-MARKER."
    assert result.turns[1].driver_leading_rejected is True
    assert result.turns[1].operator_repeat_suppressed is True
    assert views[2].facts_already_stated == ("ground_truth.grain_fact",)
    assert result.fired_event_ids == ("scope-creep",)
    assert "events_not_transmitted" not in (result.ledger_rows[1]["claim"] or {})
    assert result.ledger_rows[2]["claim"]["driver_beat_substituted"] is True
    assert result.ledger_rows[2]["claim"]["operator_beat_id"] == "scope-creep"
    assert "Please add the extra scope." in transport.message_texts[2]
    assert transport.message_texts[2].startswith("Please continue with scope refusal.")
    # The beat check -- not only the engine's delivery predicate -- rejected
    # the authored turn: the driver was re-asked once with a rejection notice
    # and the beat terms were still missing.
    assert result.turns[2].driver_fallback_reason == "driver_beat_rejected"
    assert result.turns[2].operator_beat_id == "scope-creep"
    assert len(views) == 4
    assert views[1].rejection_notice is not None and views[1].rejection_notice.startswith("leading:")
    assert views[3].rejection_notice is not None and views[3].rejection_notice.startswith("beat:")
    assert views[3].beat == DriverBeat("scope-creep", ("scope", "refusal"))
    assert views[2].rejection_notice is None


def test_a_driver_echoing_a_question_term_does_not_mark_the_fact_served() -> None:
    """Ground-truth ``terms`` trigger the *question*, so they cannot mark it answered.

    A driver that says "grain" while stating nothing must not consume the
    scripted answer: ``served_reply_keys`` survives to the end of the run
    (only a ``fresh_session`` card clears it), so marking the fact on an echo
    would stonewall the agent on that question for the rest of the run.
    """

    fact = "The grain is one row per account; FACT-ONLY-MARKER."
    script = make_script(
        turns=("Improve weekly visibility.", "Please continue.", "Please continue again."),
    )
    views: list[DriverView] = []

    def provider(view: DriverView) -> str:
        views.append(view)
        return "I am not sure about the grain; ask me later."

    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the grain?"),
            TurnResult(agent_message="I still need the grain, what is it?"),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    result = OperatorEngine(script, transport, driver=driver(provider)).run()

    assert views[0].selected_reply == fact
    assert views[0].facts_already_stated == ()
    # Turn 2 deflected in the driver's own words; the fact never went out.
    assert transport.message_texts[1] == "I am not sure about the grain; ask me later."
    assert result.turns[1].operator_repeat_suppressed is False
    assert result.ledger_rows[1]["claim"]["operator_answered_from_ground_truth"] is True
    assert "operator_repeat_suppressed" not in (result.ledger_rows[1]["claim"] or {})
    # The agent asked twice; the answer is still selected and still offered.
    assert views[1].facts_already_stated == ()
    assert views[1].known_facts == (("grain_fact", fact),)
    assert views[1].selected_reply == fact


def test_driver_may_repair_a_missed_beat_on_the_re_ask() -> None:
    """The rejection notice buys the driver a second chance at its own words."""

    event = event_from_mapping(
        {
            "version": 1,
            "id": "scope-creep",
            "trigger_turn": 3,
            "type": "scope_creep",
            "content": "Please add the extra scope.",
            "outcome": "scope_creep_fired",
            "required_terms": ["scope", "refusal"],
        }
    )
    script = make_script(
        turns=("Improve weekly visibility.", "Please continue.", "Please continue with scope refusal."),
        events=EventSchedule((event,)),
    )
    attempts: list[str | None] = []

    def provider(view: DriverView) -> str:
        attempts.append(view.rejection_notice)
        if view.turn != 3:
            return "Understood, carry on."
        return (
            "That scope is a refusal from me."
            if view.rejection_notice is not None
            else "I will not take that on."
        )

    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Status update."),
            TurnResult(agent_message="Status update."),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    result = OperatorEngine(script, transport, driver=driver(provider)).run()

    assert transport.message_texts[2].startswith("That scope is a refusal from me.")
    assert result.fired_event_ids == ("scope-creep",)
    assert result.turns[2].operator_mode == "driver"
    assert result.turns[2].driver_beat_substituted is False
    assert attempts[-1] is not None


def test_engine_recomposes_when_a_contentful_card_is_missing_from_accepted_driver_text() -> None:
    event = event_from_mapping(
        {
            "version": 1,
            "id": "content-beat",
            "trigger_turn": 3,
            "type": "scope_creep",
            "content": None,
            "outcome": "scope_recorded",
        }
    )
    script = make_script(
        turns=("Improve weekly visibility.", "Please continue.", "Please continue with the card."),
        events=EventSchedule((event,)),
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the grain?"),
            TurnResult(agent_message="What is the grain?"),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    result = OperatorEngine(
        script,
        transport,
        # Turn 2 leaks a forbidden term, so the scripted fact goes out and the
        # re-ask on turn 2 is suppressed: turn 3 composes from its own scripted
        # line, the only composition that can carry a card with no material of
        # its own.
        driver=driver(lambda view: "Let us discuss the join." if view.turn == 2 else "Understood, carry on."),
    ).run()

    assert transport.message_texts[1] == "The grain is one row per account; FACT-ONLY-MARKER."
    assert transport.message_texts[2] == "Please continue with the card."
    assert result.fired_event_ids == ("content-beat",)
    assert result.ledger_rows[2]["claim"]["driver_beat_substituted"] is True
    assert "events_not_transmitted" not in (result.ledger_rows[2]["claim"] or {})


def test_driver_fallback_is_not_an_exemption_source() -> None:
    script = make_script(
        turns=("Improve weekly visibility.", "Please continue.", "Please continue with join."),
    )
    script = OperatorScript.from_components(
        script.persona,
        answer_sheet_from_mapping(
            {
                **script.answer_sheet.to_mapping(),
                "driver_forbidden_terms": ["join"],
                "ground_truth": {"source_fact": {"terms": ["source"], "fact": "The source is authoritative."}},
            }
        ),
        turns=script.turns,
        turn_budget=script.turn_budget,
        phase_by_turn=script.phase_by_turn,
        sentinel=script.sentinel,
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    result = OperatorEngine(script, transport, driver=driver(lambda _view: "The join is obvious.")).run()

    assert transport.message_texts[2] == "Please continue with join."
    assert result.turns[2].driver_leading_rejected is True


def test_leading_rejection_flag_uses_the_final_render_reason() -> None:
    replies = iter(("The grain is obvious.", "Understood, carry on."))
    script = make_script(turns=("Improve weekly visibility.", "Please continue."))
    result = OperatorEngine(
        script,
        InMemoryTransport(
            [TurnResult(agent_message="What is the source?"), TurnResult(agent_message="Done.", reported=True)]
        ),
        driver=driver(lambda _view: next(replies)),
    ).run()

    assert result.turns[1].operator_message.text == "Understood, carry on."
    assert result.turns[1].driver_leading_rejected is False
    assert result.turns[1].driver_fallback_reason is None
    # The row is the durable evidence: a retried-then-accepted turn is a plain
    # driver turn, not a recorded rejection. Flags read from ``attempts``
    # instead of the final reason would stamp this row as a leak.
    claim = result.ledger_rows[1]["claim"] or {}
    assert claim["operator_mode"] == "driver"
    assert "driver_leading_rejected" not in claim
    assert "driver_obstacle_rejected" not in claim
    assert "driver_repeat_rejected" not in claim
    assert "driver_beat_substituted" not in claim


def test_driver_construction_rejects_missing_terms_and_conflicting_operator() -> None:
    script = make_script()
    missing = script.answer_sheet
    no_terms_mapping = missing.to_mapping()
    no_terms_mapping.pop("driver_forbidden_terms", None)
    no_terms = answer_sheet_from_mapping(no_terms_mapping)
    no_terms_script = OperatorScript.from_components(
        script.persona,
        no_terms,
        turns=script.turns,
        turn_budget=script.turn_budget,
        phase_by_turn=script.phase_by_turn,
    )
    with pytest.raises(ValueError, match="driver_forbidden_terms"):
        OperatorEngine(no_terms_script, InMemoryTransport([TurnResult(agent_message="What is the source?")]), driver=driver(lambda _view: "ok"))
    with pytest.raises(ValueError, match="never both"):
        OperatorEngine(
            script,
            InMemoryTransport([TurnResult(agent_message="What is the source?")]),
            driver=driver(lambda _view: "ok"),
            generated_operator=GeneratedOperator(lambda _view: "ok"),
        )


def test_driver_repeat_guard_rejects_a_previously_selected_line() -> None:
    script = make_script(turns=("Improve weekly visibility.", "Please continue."))
    result = OperatorEngine(
        script,
        InMemoryTransport(
            [
                TurnResult(agent_message="What is the source?"),
                TurnResult(agent_message="Done.", reported=True),
            ]
        ),
        # Turn 1's selected base is the opening; re-sending it is the repeat.
        driver=driver(lambda _view: "Improve weekly visibility."),
    ).run()

    assert result.turns[1].operator_message.text == "The source is the approved business record."
    assert result.turns[1].driver_repeat_rejected is True
    assert result.turns[1].driver_leading_rejected is False
    assert result.turns[1].driver_fallback_reason == "driver_repeat_rejected"
    assert result.ledger_rows[1]["claim"]["driver_repeat_rejected"] is True


def test_driver_may_reuse_its_own_authored_sentence_across_turns() -> None:
    """The repeat guard compares against selected script text, not driver prose.

    A persona is allowed to say "Understood, carry on." twice; only re-sending
    a line the deterministic engine already chose is a repeat. This is the
    companion of the guard above and pins the deliberate asymmetry.
    """

    script = make_script(turns=("Improve weekly visibility.", "Please continue.", "Please continue again."))
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Status update."),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    result = OperatorEngine(script, transport, driver=driver(lambda _view: "Understood, carry on.")).run()

    assert transport.message_texts[1:] == ("Understood, carry on.", "Understood, carry on.")
    assert all(record.driver_repeat_rejected is False for record in result.turns)


def test_driver_obstacle_guard_rejects_a_planted_obstacle_term() -> None:
    script = make_script(turns=("Improve weekly visibility.", "Please continue."))
    result = OperatorEngine(
        script,
        InMemoryTransport(
            [
                TurnResult(agent_message="What is the source?"),
                TurnResult(agent_message="Done.", reported=True),
            ]
        ),
        driver=driver(lambda _view: "You should just raise the timeout."),
    ).run()

    assert result.turns[1].operator_message.text == "The source is the approved business record."
    assert result.turns[1].driver_obstacle_rejected is True
    assert result.turns[1].driver_leading_rejected is False
    assert result.turns[1].driver_repeat_rejected is False
    assert result.ledger_rows[1]["claim"]["driver_obstacle_rejected"] is True


def test_offered_fact_text_is_redacted_before_it_reaches_the_driver() -> None:
    """A marker planted inside a served ground-truth fact must not leave the engine."""

    script = make_script(turns=("Improve weekly visibility.", "Please continue."))
    views: list[DriverView] = []

    def provider(view: DriverView) -> str:
        views.append(view)
        return "Understood, carry on."

    OperatorEngine(
        script,
        InMemoryTransport(
            [
                TurnResult(agent_message="What is the grain?"),
                TurnResult(agent_message="Done.", reported=True),
            ]
        ),
        driver=driver(provider),
        extra_sentinels=[b"FACT-ONLY-MARKER"],
    ).run()

    assert [key for key, _ in views[0].known_facts] == ["grain_fact"]
    assert "FACT-ONLY-MARKER" not in json.dumps(views[0].to_mapping())
    assert all("FACT-ONLY-MARKER" not in fact for _, fact in views[0].known_facts)


def test_an_approval_turn_does_not_consume_the_reply_it_never_transmits() -> None:
    """A reply selected before an approval turn is still owed to the agent.

    The approval turn transmits its declared line, so the pending answer-sheet
    reply never goes out. Marking it served there would make the operator
    refuse to repeat a fact the agent has never been told.
    """

    turns = (
        "Improve weekly visibility.",
        "Please continue.",
        {"text": "The specification is approved.", "approval": True},
        "Please continue again.",
    )
    script = make_script(turns=turns)
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Status update."),
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    result = OperatorEngine(script, transport).run()

    assert transport.message_texts == (
        "Improve weekly visibility.",
        "The work is still in progress.",
        "The specification is approved.",
        "The source is the approved business record.",
    )
    assert all(record.operator_repeat_suppressed is False for record in result.turns)
    approval = next(row for row in result.ledger_rows if row["action_kind"] == "spec_approved")
    assert approval["artifact_ref"] == "The specification is approved."


def test_a_driver_that_echoes_a_planted_marker_is_rejected_and_never_transmits_it() -> None:
    """The redaction invariant is symmetric: nothing planted goes out either.

    Redaction keeps markers out of the driver's view, so an authored one is a
    coincidence -- but an unguarded one would land in the operator's own turn,
    in the transcript grading scans, and back in the provider's context on
    every later turn as a prior operator message.
    """

    marker = "pii-sentinel-6f3a9c2e"
    script = make_script(
        turns=("Improve weekly visibility.", "Please continue.", "Please continue again."),
    )
    views: list[DriverView] = []

    def provider(view: DriverView) -> str:
        views.append(view)
        if view.turn == 2:
            return f"Drop the {marker} column before you continue."
        return "Understood, carry on."

    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Which source is authoritative?"),
            TurnResult(agent_message="Status update."),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    result = OperatorEngine(
        script,
        transport,
        driver=driver(provider),
        extra_sentinels=[marker.encode("utf-8")],
    ).run()

    assert marker not in "\n".join(transport.message_texts)
    assert transport.message_texts[1] == "The source is the approved business record."
    assert result.turns[1].driver_obstacle_rejected is True
    assert result.turns[1].driver_fallback_reason == "driver_obstacle_rejected"
    # The rejection notice is fed straight back to the provider, so it must
    # not quote the marker it is rejecting.
    assert views[1].rejection_notice is not None
    assert marker not in json.dumps(views[1].to_mapping())
