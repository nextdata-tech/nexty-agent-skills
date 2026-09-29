"""Publication-triggered event scheduling uses runner-owned prior-turn evidence."""

from dp_scenarios.operator.engine import OperatorEngine
from dp_scenarios.operator.events import EventCard, EventSchedule, event_from_mapping
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult
from dp_scenarios.runner.session import RecordingSession, ReplaySession

from test_operator_engine import make_script


def _schedule_snapshot() -> dict[str, object]:
    runs = [
        ("unrelated", "old-run", "old-definition", 1),
        ("target", "initial-run", "definition-a", 3),
        ("target", "rebuild-run", "definition-b", 4),
        ("target", "final-run", "definition-c", 7),
    ]
    return {
        "run_records": {
            "schema": "dp-scenario-run-records-v1",
            "runs": [
                {
                    "workflow_id": workflow,
                    "run_id": run,
                    "definition_id": definition,
                    "status_history": [{"turn": published_turn, "status": "Published"}],
                }
                for workflow, run, definition, published_turn in runs
            ],
        },
        "publication_history": {
            "schema": "dp-scenario-publication-history-v1",
            "releases": [
                {
                    "workflow_id": workflow,
                    "run_id": run,
                    "definition_id": definition,
                    # Publication history's turn is run start; scheduling
                    # relies on status_history instead.
                    "turn": 1,
                }
                for workflow, run, definition, _ in runs
            ],
        },
    }


def _card(
    *,
    card_id: str,
    trigger_turn: int,
    content: str,
    outcome: str,
    after_published: str | None = None,
    after_event: str | None = None,
    event_type: str = "scope_creep",
    gap_seconds: int = 0,
    fresh_session: bool | None = None,
    required_terms: tuple[str, ...] = (),
) -> EventCard:
    value: dict[str, object] = {
        "version": 1,
        "id": card_id,
        "trigger_turn": trigger_turn,
        "type": event_type,
        "content": content,
        "outcome": outcome,
    }
    if after_published is not None:
        value["after_published"] = after_published
    if after_event is not None:
        value["after_event"] = after_event
    if gap_seconds:
        value["gap_seconds"] = gap_seconds
    if fresh_session is not None:
        value["fresh_session"] = fresh_session
    if required_terms:
        value["required_terms"] = list(required_terms)
    return event_from_mapping(value)


def test_publication_events_replay_with_the_same_actual_delivery_turns() -> None:
    fixed = _card(
        card_id="first-challenge",
        trigger_turn=4,
        content="The spreadsheet challenges February.",
        outcome="spreadsheet_challenge",
    )
    initial = _card(
        card_id="decision-reversal",
        trigger_turn=2,
        content="I am changing that same-month decision.",
        outcome="decision_reversed",
        after_published="initial",
        after_event="first-challenge",
        event_type="decision_reversal",
    )
    resumed = _card(
        card_id="resume-after-revision",
        trigger_turn=2,
        content="I am back. Did the revised bridge finish?",
        outcome="revision_resumed",
        after_published="revised",
        after_event="decision-reversal",
        event_type="back_after_lunch",
        gap_seconds=14400,
        fresh_session=False,
    )
    events = EventSchedule(tuple(sorted((fixed, initial, resumed), key=lambda item: (item.trigger_turn, item.card_id))))
    script = make_script(
        turns=(
            "Improve weekly visibility.",
            "Continue the analysis.",
            "Continue the analysis again.",
            "Review the spreadsheet.",
            "Revise the decision.",
            "Rebuild the approved definition.",
            "Publish the revised definition.",
            "Resume after the revised publication.",
        ),
        turn_budget=8,
        events=events,
    )
    snapshot = _schedule_snapshot()
    transport = RecordingSession(
        InMemoryTransport([TurnResult(agent_message="The work is continuing.") for _ in range(8)])
    )

    original = OperatorEngine(
        script,
        transport,
        publication_history_reader=lambda: snapshot,
    ).run()

    # Turn 4's fixed challenge takes precedence. The first publication card
    # arrives on turn 5, and its actual delivery turn gates the revised card.
    assert original.turns[3].event_ids == ("first-challenge",)
    assert "decision-reversal" in original.turns[4].event_ids
    assert original.turns[5].event_ids == ()
    assert "resume-after-revision" in original.turns[7].event_ids

    recording = transport.recording(metadata={"publication_schedule": snapshot})
    replay_transport = ReplaySession(recording)
    replay = OperatorEngine(
        script,
        replay_transport,
        publication_history_reader=lambda: recording.metadata["publication_schedule"],
    ).run()

    assert replay_transport.remaining_turns == 0
    assert replay.operator_message_bytes == original.operator_message_bytes
    assert replay.ledger_bytes == original.ledger_bytes


def test_undelivered_publication_card_retries_until_its_beat_is_delivered() -> None:
    card = _card(
        card_id="initial-publication",
        trigger_turn=2,
        content="The initial release is published.",
        outcome="initial_release_observed",
        after_published="initial",
        required_terms=("confirmed",),
    )
    events = EventSchedule((card,))
    script = make_script(
        turns=(
            "Improve weekly visibility.",
            "Please continue.",
            "The publication status is confirmed.",
        ),
        turn_budget=3,
        events=events,
    )
    snapshot = _schedule_snapshot()
    # The first eligible turn lacks the declared delivery phrase; the next
    # turn includes it, so the card must be offered again.

    result = OperatorEngine(
        script,
        InMemoryTransport([TurnResult(agent_message="Still working.") for _ in range(3)]),
        publication_history_reader=lambda: snapshot,
    ).run()

    assert result.turns[1].event_ids == ()
    assert result.turns[2].event_ids == ("initial-publication",)
