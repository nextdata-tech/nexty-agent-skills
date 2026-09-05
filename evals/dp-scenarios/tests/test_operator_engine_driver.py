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


def test_the_whole_brief_is_offered_every_turn_and_stays_redacted() -> None:
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
    # Four agent messages precede the second authorable turn; the view carries
    # the last two and no more.
    assert len(views) == 2
    assert views[0].prior_agent_messages == ("What is the source?", "Status update <redacted-sentinel>.")
    assert views[1].prior_agent_messages == ("Done.", "")
    assert all(len(view.prior_agent_messages) <= 2 for view in views)
    assert all("FIXTURE-SECRET" not in json.dumps(view.to_mapping()) for view in views)
    assert all("ACTIVE-SENTINEL" not in json.dumps(view.to_mapping()) for view in views)

    # No agent message in this run says "grain" or "join", and the whole brief
    # is offered anyway. The offer used to be keyword-gated on the current
    # message, which starved a live run: four turns were handed no fact at all
    # and four more the same single fact, because one trigger term happened to
    # be a common word. A fact's ``terms`` trigger the *question*, so gating
    # the offer on them asked whether the agent had used the author's
    # vocabulary, not whether the operator knows the answer.
    expected = (
        ("grain_fact", "The grain is one row per account; FACT-ONLY-MARKER."),
        ("join_fact", "The join uses account_id."),
    )
    assert all(view.known_facts == expected for view in views)

    # known_facts is ground truth only. The decision and status banks are the
    # rubric the run is graded against and must never be offered to a driver.
    sheet = script.answer_sheet
    assert all(key in sheet.ground_truth for key, _ in views[0].known_facts)
    rubric = ("The work is still in progress.", "Choose the approved option.")
    assert all(text not in json.dumps(views[0].known_facts) for text in rubric)


def test_offering_the_whole_brief_does_not_exempt_every_forbidden_term() -> None:
    """The leading guard must not be retired by widening the fact offer.

    A forbidden term is exempt when the agent has already reached it, or when
    it appears in a fact the agent actually asked for -- answering a question
    in the asker's own words is not leading. Exempting from every *offered*
    fact instead would leave ``driver_forbidden_terms`` nominally enforced and
    actually empty: this fixture's brief contains both "grain" and "join", so
    every declared term would be exempt on every turn and a driver could hand
    the agent the answer with the scan still running.
    """

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
                TurnResult(agent_message="What is the grain?"),
                TurnResult(agent_message="Done.", reported=True),
            ]
        ),
        driver=driver(provider),
    ).run()

    # Turn 2 is not substitutable, so the authorable turns are 3 and 5 and
    # their preceding agent messages are "What is the grain?" and "Done.".
    assert len(views) == 2
    assert all(len(view.known_facts) == 2 for view in views)

    # The agent asked about the grain, so the grain fact -- and only that one --
    # becomes sayable. The join fact was offered on the very same turn and its
    # term is still in force: this is the assertion that fails if exemption is
    # ever computed from the offer.
    assert "grain" not in views[0].forbidden_terms
    assert "join" in views[0].forbidden_terms
    assert "aggregation" in views[0].forbidden_terms

    # Nothing factual was asked before the second authorable turn, so all three
    # stand again -- an exemption is per question, never sticky.
    assert set(views[1].forbidden_terms) == {"grain", "join", "aggregation"}


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

    # The whole brief is offered every turn; the memory below is what
    # decides whether a fact is *restated*, not the offer.
    assert views[0].known_facts == (
        ("grain_fact", "The grain is one row per account; FACT-ONLY-MARKER."),
        ("join_fact", "The join uses account_id."),
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
    assert views[1].known_facts == (("grain_fact", fact), ("join_fact", "The join uses account_id."))
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

    assert [key for key, _ in views[0].known_facts] == ["grain_fact", "join_fact"]
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


def test_a_driver_that_conveys_a_fact_stops_being_handed_it_again() -> None:
    """The live failure: the operator restating what it already said.

    A 15-turn driven run re-selected one ground-truth fact ten times and
    another six, with zero suppressions, while the agent replied "already
    done" four turns running -- the operator-repeats-itself failure the driver
    exists to remove, reproduced by the driver. The cause was that
    ``served_reply_keys`` only filled when the *scripted* sentence went out,
    which under a driver means only on a fallback, so the memory stayed empty
    for the whole run.

    A driver that restates the fact in its own words has transmitted it, so it
    must be recorded as served and not offered again.
    """

    fact = "The grain is one row per account; FACT-ONLY-MARKER."
    script = make_script(
        turns=("Improve weekly visibility.", "Please continue.", "Please continue again."),
    )
    views: list[DriverView] = []

    def provider(view: DriverView) -> str:
        views.append(view)
        # Carries the substance in the driver's own words, not the scripted line.
        return "Each row stands for a single account, so the grain is one account per row."

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
    # Turn 2 conveyed it, so the re-ask on turn 2 is suppressed rather than
    # answered again, and the next authored turn is handed no fact at all.
    assert result.turns[1].operator_repeat_suppressed is True, (
        "the driver restated the fact and the memory still did not record it"
    )
    assert "ground_truth.grain_fact" in views[1].facts_already_stated
    assert views[1].selected_reply == "", "the same fact was offered to the driver again"


def test_conveyance_ignores_words_the_agent_supplied_itself() -> None:
    """Echoing the question back is not conveying the answer.

    The distinctive words are the reply's own *minus* the agent's message, and
    this is the case where that subtraction is the only thing standing between
    a pure echo and a consumed fact: every content word of the reply also
    appears in the question, so without the subtraction the echo scores a
    perfect 1.0 and the agent is stonewalled on a question it never got an
    answer to.
    """

    from dp_scenarios.operator.engine import _authored_text_conveys

    reply = "The owner object belongs to sales."
    question = "Does the owner object belong to sales?"

    assert _authored_text_conveys(reply, question, "The owner object belongs to sales?") is False

    # The same reply *does* count when the driver adds the substance the
    # question did not contain.
    informative = "Yes -- each owner object is the individual sales rep who holds that deal."
    assert _authored_text_conveys(
        "The owner object is the individual sales rep who holds that deal.",
        "Who does the owner object belong to?",
        informative,
    ) is True


def test_a_short_fact_needs_every_distinctive_word_not_just_two() -> None:
    """On a short reply the two-word floor stops discriminating.

    With three distinctive words any two clear both floors (2/3 = 0.67), so a
    deflection that merely names them would consume the fact permanently --
    only a ``fresh_session`` card clears the set, so the agent would be
    stonewalled on that question for the rest of the run. Short replies
    therefore require every distinctive word.

    The cost is deliberate and asymmetric: a genuine short restatement that
    drops a word is re-offered, which repeats a sentence, while the failure it
    prevents silently withholds an answer.
    """

    from dp_scenarios.operator.engine import _authored_text_conveys

    fact = "The grain is one row per account."
    question = "What grain should I use?"

    # Names two of the three distinctive words while stating nothing.
    assert _authored_text_conveys(fact, question, "Not sure about row or account, honestly.") is False
    # The repo's own short fixture fact, deflected. Note this one carries a
    # single distinctive word, so it is rejected by the two-word floor and
    # would pass against the previous implementation too -- kept as a
    # regression pin on a real fixture, not as evidence for this rule.
    assert _authored_text_conveys(
        "The join uses account_id.",
        "What is the join key?",
        "I am not sure - something about account_id, you tell me.",
    ) is False
    # Full coverage still counts.
    assert _authored_text_conveys(fact, question, "One row per account is the level.") is True


@pytest.mark.parametrize("distinctive_words", [3, 4, 5, 6, 7, 9])
def test_a_two_word_deflection_never_consumes_a_fact_at_any_length(distinctive_words: int) -> None:
    """The floors have to hold across set sizes, not at one of them.

    The first version of this check fixed only three distinctive words: at four
    and five a two-word deflection still cleared both floors (0.50 and 0.40,
    both above the 0.34 ratio), because the ratio does not bind until six while
    the minimum was two. Testing a single size is what let that through, so this
    sweeps the range.
    """

    from dp_scenarios.operator.engine import _authored_text_conveys, _content_words

    words = [f"zeta{index}" for index in range(distinctive_words)]
    reply = " ".join(words) + "."
    question = "What is it?"
    assert len(_content_words(reply) - _content_words(question)) == distinctive_words

    # A deflection that incidentally names two of them. Starts at three
    # distinctive words on purpose: at two, naming two is *full* coverage, so
    # that case pins the refuses-to-judge rule rather than this one -- it is
    # asserted separately below.
    assert _authored_text_conveys(reply, question, " ".join(words[:2]) + "?") is False


def test_a_reply_that_barely_differs_from_the_question_is_never_judged() -> None:
    """Two distinctive words is too little evidence either way.

    Naming both of them is full coverage, not a deflection, so this pins the
    refuses-to-judge rule rather than the incidental-mention floor.
    """

    from dp_scenarios.operator.engine import _authored_text_conveys

    assert _authored_text_conveys("Alpha beta.", "Question?", "Alpha beta?") is False


def test_a_genuine_restatement_still_counts_at_the_lengths_that_matter() -> None:
    """The floors must not be so strict that real conveyance stops registering.

    Guards the other direction of the same change: raising the minimum to three
    is only safe if the driven turns it was calibrated on still pass.
    """

    from dp_scenarios.operator.engine import _authored_text_conveys

    assert _authored_text_conveys(
        "The deals endpoint is an HTTP API. Its address is in the infra-profile.yaml"
        " sitting in your working directory.",
        "Where is the deals endpoint?",
        "The deals endpoint is an HTTP API, and its address is in infra-profile.yaml"
        " in the working directory.",
    ) is True
    assert _authored_text_conveys(
        "updatedAt is the last time any field on that deal record changed, not the"
        " time it entered its current stage.",
        "What does updatedAt mean?",
        "Understood: updatedAt shows the latest change to any field on the deal"
        " record, not when it entered its current stage.",
    ) is True


def test_a_reply_that_adds_nothing_to_the_question_does_not_divide_by_zero() -> None:
    """The empty distinctive set is guarded by evaluation order alone.

    Every content word of the reply also appears in the question, so
    ``distinctive`` is empty and the ratio would divide by zero. Nothing but
    the ``and`` short-circuiting on the minimum prevents it, and no other test
    reaches an *empty* set -- ``test_conveyance_ignores_words_the_agent_supplied_itself``
    gets to one, because "belongs" and "belong" are distinct tokens without
    stemming -- so this pins the ordering rather than trusting it.
    """

    from dp_scenarios.operator.engine import _authored_text_conveys, _content_words

    reply = "The owner belongs to sales."
    question = "Is it true that the owner belongs to sales?"
    assert _content_words(reply) - _content_words(question) == set(), "fixture no longer empties the set"

    assert _authored_text_conveys(reply, question, "The owner belongs to sales.") is False
