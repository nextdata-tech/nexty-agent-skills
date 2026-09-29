"""B11 operator decision stages and explicit chain overlays."""

from __future__ import annotations

from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import AnswerSheetError, answer_sheet_from_mapping
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.matcher import MatcherBank, MatcherError, validate_decision_reachability
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult
from dp_scenarios.runner.session import RecordingSession, ReplaySession


ROOT = Path(__file__).parents[1]
PERSONA = load_persona(ROOT / "scenarios/_personas/smoke.yaml")
PREFIX_ANSWER = "Reject an unrecognised stage."
STAGE_ANSWERS = (
    "I need to check with Finance. Can you decide?",
    "They think it may be real, but have not confirmed whether it belongs in the numbers.",
    "Keep the original five as official. Publish provisional rows, flag out-of-list stages as a warning, and update the approved plan and executable check.",
)
STAGE_QUESTION = "A value outside the stage enum appeared; what should I do?"


def _sheet(*, malformed_stage_count: bool = False):
    stages = [STAGE_ANSWERS[0], STAGE_ANSWERS[1]] if malformed_stage_count else list(STAGE_ANSWERS)
    return answer_sheet_from_mapping(
        {
            "version": 1,
            "scenario_id": "operator-decision-overlays-test",
            "opening_message": "I want pipeline numbers for every week.",
            "turns": [
                "I want pipeline numbers for every week.",
                "Please continue.",
                "Please continue again.",
                "Please continue once more.",
                "Please keep going.",
                "Please wrap up.",
            ],
            "source_answers": {"source": "The CRM endpoint is the source."},
            "decision_answers": {
                "workflow_revision": {
                    "terms": ["new", "workflow"],
                    "synonyms": {
                        "new": ["separate", "versioned", "fresh"],
                        "workflow": ["product", "release"],
                    },
                    "answer": "You may create a separate workflow and preserve the published one.",
                },
                "stage_enum": {
                    "terms": ["stage", "enum"],
                    "answer": PREFIX_ANSWER,
                    "retired_after_overlay": "crm_deals_v2",
                },
                "new_stage_consequence": {
                    "terms": ["stage", "treatment"],
                    "synonyms": {
                        "stage": ["category", "out-of-list value"],
                        "treatment": [
                            "handle",
                            "treat",
                            "block",
                            "stop",
                            "reject",
                            "warn",
                            "warning",
                            "publish",
                            "include",
                            "do",
                        ],
                    },
                    "stages": stages,
                    "available_after_overlay": "crm_deals_v2",
                },
                "review_fix_authorization": {
                    "terms": ["review", "finding"],
                    "answer": "Fix only the named findings, then capture and review again.",
                },
            },
            "status_answers": {"status": "The work is still in progress."},
            "opening_forbidden_terms": ["deal_value", "verbal_commit", "champion"],
            "open_decision_markers": ["[DECISION NEEDED]"],
            "obstacle_terms": [],
        }
    )


def test_staged_and_overlay_decisions_round_trip_without_changing_legacy_shape() -> None:
    sheet = _sheet()
    mapping = sheet.to_mapping()

    assert mapping["decision_answers"]["workflow_revision"] == {
        "terms": ["new", "workflow"],
        "synonyms": {
            "new": ["separate", "versioned", "fresh"],
            "workflow": ["product", "release"],
        },
        "answer": "You may create a separate workflow and preserve the published one.",
    }
    assert mapping["decision_answers"]["new_stage_consequence"]["stages"] == list(STAGE_ANSWERS)
    assert "answer" not in mapping["decision_answers"]["new_stage_consequence"]
    assert mapping["decision_answers"]["stage_enum"]["retired_after_overlay"] == "crm_deals_v2"


@pytest.mark.parametrize(
    "entry",
    [
        {"terms": ["stage"], "answer": "One.", "stages": ["Two.", "Three."]},
        {"terms": ["stage"], "stages": ["Only one stage."]},
        {"terms": ["stage"], "stages": []},
        {"terms": ["stage"], "stages": ["One.", "Two.", " "]},
        {
            "terms": ["stage"],
            "stages": ["One.", "Two."],
            "available_after_overlay": "same",
            "retired_after_overlay": "same",
        },
    ],
)
def test_malformed_staged_decision_declarations_fail_closed(entry: object) -> None:
    mapping = _sheet().to_mapping()
    mapping["decision_answers"]["new_stage_consequence"] = entry

    with pytest.raises(AnswerSheetError):
        answer_sheet_from_mapping(mapping)


def test_exhaustive_reachability_checks_every_decision_with_natural_synonyms() -> None:
    sheet = _sheet()
    validate_decision_reachability(
        sheet,
        exhaustive=True,
        probes_by_decision={
            "workflow_revision": [
                "Could we create a fresh product workflow?",
                "May I publish a versioned release?",
            ],
            "stage_enum": [
                "Should the stage enum reject this value?",
            ],
            "new_stage_consequence": [
                "A value outside the stage enum appeared; what should I do?",
                "How should we treat this out-of-list stage value?",
            ],
            "review_fix_authorization": [
                "May I fix the findings from the review?",
            ],
        },
    )


def test_exhaustive_reachability_finds_an_unreachable_staged_decision() -> None:
    mapping = _sheet().to_mapping()
    # This earlier id captures both required terms, leaving the opt-in overlay
    # answer unreachable even after it is activated.
    mapping["decision_answers"]["a_shadow"] = {
        "terms": ["stage", "treatment"],
        "answer": "Shadowed.",
        "available_after_overlay": "crm_deals_v2",
    }
    sheet = answer_sheet_from_mapping(mapping)

    with pytest.raises(MatcherError, match="new_stage_consequence.*unreachable"):
        validate_decision_reachability(sheet, exhaustive=True)


def test_natural_synonym_asks_route_to_the_declared_decisions() -> None:
    bank = MatcherBank(PERSONA, _sheet())

    workflow = bank.reply_for("Could we create a fresh product workflow?")
    review = bank.reply_for("May I fix the findings from the review?")
    assert workflow.decision_id == "workflow_revision"
    assert workflow.reply.startswith("You may create a separate workflow")
    assert review.decision_id == "review_fix_authorization"

    bank.activate_decision_overlay("crm_deals_v2")
    first = bank.reply_for("How should we treat this out-of-list stage value?")
    second = bank.reply_for(
        "They have not confirmed it belongs in the numbers. What should we do about the stage?",
        decision_stage_counts={"new_stage_consequence": 1},
    )
    final = bank.reply_for(
        "Should I include the provisional stage and publish the refresh?",
        decision_stage_counts={"new_stage_consequence": 2},
    )

    assert (first.decision_id, first.decision_stage, first.decision_final) == (
        "new_stage_consequence",
        1,
        False,
    )
    assert (second.decision_id, second.decision_stage, second.decision_final) == (
        "new_stage_consequence",
        2,
        False,
    )
    assert (final.decision_id, final.decision_stage, final.decision_final) == (
        "new_stage_consequence",
        3,
        True,
    )


def test_stage_decision_is_absent_until_explicit_overlay_then_retires_prefix_answer() -> None:
    bank = MatcherBank(PERSONA, _sheet())

    before = bank.reply_for(STAGE_QUESTION)
    assert before.decision_id == "stage_enum"
    assert before.reply == PREFIX_ANSWER
    assert before.decision_stage is None
    assert before.decision_final is None
    assert bank.active_decision_overlays == ()

    bank.activate_decision_overlay("crm_deals_v2")
    bank.activate_decision_overlay("crm_deals_v2")
    after = bank.reply_for(STAGE_QUESTION)

    assert bank.active_decision_overlays == ("crm_deals_v2",)
    assert after.decision_id == "new_stage_consequence"
    assert after.reply == STAGE_ANSWERS[0]
    assert after.decision_stage == 1
    assert after.decision_final is False
    assert PREFIX_ANSWER not in after.reply


def test_unknown_overlay_id_is_rejected() -> None:
    bank = MatcherBank(PERSONA, _sheet())

    with pytest.raises(MatcherError, match="undeclared decision overlay"):
        bank.activate_decision_overlay("turn-17")


def test_engine_counts_only_delivered_stages_and_clamps_on_final_answer() -> None:
    sheet = _sheet()
    bank_script = OperatorScript.from_components(
        PERSONA,
        sheet,
        turn_budget=6,
        phase_by_turn={turn: min(turn, 7) for turn in range(1, 7)},
    )
    question = "What treatment should we use for this out-of-list stage?"
    transport = InMemoryTransport(
        [
            TurnResult(agent_message=question),
            TurnResult(agent_message=question),
            TurnResult(agent_message="The question is waiting on Finance."),
            TurnResult(agent_message=question),
            TurnResult(agent_message=question),
            TurnResult(agent_message="Done."),
        ]
    )
    engine = OperatorEngine(bank_script, transport)
    engine.activate_decision_overlay("crm_deals_v2")

    result = engine.run()

    assert [turn.selected_decision_stage for turn in result.turns] == [1, 2, None, 3, 3, None]
    assert [turn.selected_decision_final for turn in result.turns] == [False, False, None, True, True, None]
    assert [turn.delivered_decision_stage for turn in result.turns] == [None, 1, 2, None, 3, 3]
    assert [turn.delivered_decision_final for turn in result.turns] == [None, False, False, None, True, True]
    assert transport.message_texts[1] == STAGE_ANSWERS[0]
    assert transport.message_texts[2] == STAGE_ANSWERS[1]
    assert transport.message_texts[4] == STAGE_ANSWERS[2]
    assert transport.message_texts[5] == STAGE_ANSWERS[2]


def test_overlay_discards_a_pending_prefix_answer_before_the_next_operator_message() -> None:
    sheet = _sheet()
    script = OperatorScript.from_components(
        PERSONA,
        sheet,
        turns=(sheet.opening_message, "Please continue.", "Please keep going."),
        turn_budget=3,
        phase_by_turn={1: 1, 2: 2, 3: 3},
    )
    responses = [
        TurnResult(agent_message=STAGE_QUESTION),
        TurnResult(agent_message=STAGE_QUESTION),
        TurnResult(agent_message="I will check the updated figures."),
    ]

    def run_with_boundary(transport):
        engine_ref: dict[str, OperatorEngine] = {}

        def after_turn(_recording: object, turn: int) -> None:
            if turn == 1:
                engine_ref["engine"].activate_decision_overlay("crm_deals_v2")

        recording_transport = RecordingSession(transport, on_turn_complete=after_turn)
        engine = OperatorEngine(script, recording_transport)
        engine_ref["engine"] = engine
        return engine, engine.run(), recording_transport

    _, result, recording_transport = run_with_boundary(InMemoryTransport(responses))

    assert result.turns[0].selected_decision_stage is None
    assert result.turns[0].selected_decision_final is None
    assert result.turns[1].delivered_decision_id is None
    recorded_messages = [turn.operator_message.text for turn in recording_transport.turns]
    assert recorded_messages[1] == "Please continue."
    assert PREFIX_ANSWER not in "\n".join(recorded_messages)
    assert result.turns[1].match.decision_id == "new_stage_consequence"
    assert result.turns[1].selected_decision_stage == 1

    replay_session = ReplaySession(recording_transport.recording())
    _, replay, replay_recording = run_with_boundary(replay_session)

    assert replay_session.remaining_turns == 0
    assert replay.operator_message_bytes == result.operator_message_bytes
    assert [turn.selected_decision_stage for turn in replay.turns] == [
        turn.selected_decision_stage for turn in result.turns
    ]
    assert [turn.delivered_decision_stage for turn in replay.turns] == [
        turn.delivered_decision_stage for turn in result.turns
    ]
