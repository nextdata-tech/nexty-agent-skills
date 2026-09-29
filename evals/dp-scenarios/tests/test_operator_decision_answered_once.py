"""A declared decision is repeated only for the same request clause."""

from pathlib import Path

from dp_scenarios.operator.answer_sheet import load_answer_sheet
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult
from dp_scenarios.scenario import load_scenario


ROOT = Path(__file__).parents[1]
FINANCE_CLOSE = load_answer_sheet(ROOT / "scenarios/finance-close/answer-sheet.yaml")
PERSONA = load_persona(ROOT / "scenarios/_personas/smoke.yaml")
WEEKEND_ANSWER = FINANCE_CLOSE.decision_answers["weekend_fx"].answer
REVIEW_FIX_ANSWER = FINANCE_CLOSE.decision_answers[
    "review_fix_authorization"
].answer
CRM_PIPELINE_DRIFT = load_scenario(ROOT / "scenarios/crm-pipeline-drift")


def _script(turn_count: int) -> OperatorScript:
    turns = (FINANCE_CLOSE.opening_message,) + tuple(
        f"Please continue on turn {turn}." for turn in range(2, turn_count + 1)
    )
    return OperatorScript.from_components(
        PERSONA,
        FINANCE_CLOSE,
        turns=turns,
        turn_budget=25,
        phase_by_turn={turn: 7 for turn in range(1, turn_count + 1)},
    )


def test_different_weekend_rate_clause_falls_through_to_the_data_answer() -> None:
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Should we exclude the weekend rate?"),
            TurnResult(
                agent_message="What data should I use to verify the weekend rate?"
            ),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )

    OperatorEngine(_script(5), transport).run()

    assert transport.message_texts[2] == WEEKEND_ANSWER
    assert transport.message_texts[3] == FINANCE_CLOSE.source_answers["data"]


def test_normalized_identical_weekend_rate_request_is_answered_again() -> None:
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Should I exclude the weekend rate?"),
            TurnResult(
                agent_message="**Should   I exclude the WEEKEND, rate?**"
            ),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )

    OperatorEngine(_script(5), transport).run()

    assert transport.message_texts[2:4] == (WEEKEND_ANSWER, WEEKEND_ANSWER)


def test_review_fix_authorization_resets_decisions_for_a_new_review_generation() -> None:
    review_fix_request = (
        "The reviewer found a blocking finding. Should I apply the review fix?"
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message="Should we exclude the weekend rate?"),
            TurnResult(agent_message=review_fix_request),
            TurnResult(agent_message="Should we exclude the weekend rate?"),
            TurnResult(
                agent_message=(
                    "The reviewer found another blocking finding. "
                    "Should I apply this review correction?"
                )
            ),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )

    result = OperatorEngine(_script(7), transport).run()

    assert transport.message_texts[2] == WEEKEND_ANSWER
    assert transport.message_texts[3] == REVIEW_FIX_ANSWER
    assert transport.message_texts[4] == WEEKEND_ANSWER
    assert transport.message_texts[5] == REVIEW_FIX_ANSWER
    assert result.turns[2].match.rule_id == "decision.answer.review_fix_authorization"
    assert result.turns[4].match.rule_id == "decision.answer.review_fix_authorization"


def test_review_fix_authorization_is_answered_on_every_request() -> None:
    review_fix_request = (
        "The reviewer found a blocking finding. Should I apply the review fix?"
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message=review_fix_request),
            TurnResult(agent_message=review_fix_request),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )

    result = OperatorEngine(_script(5), transport).run()

    assert transport.message_texts[2:4] == (REVIEW_FIX_ANSWER, REVIEW_FIX_ANSWER)
    assert result.turns[1].match.rule_id == "decision.answer.review_fix_authorization"
    assert result.turns[2].match.rule_id == "decision.answer.review_fix_authorization"


def test_mixed_workflow_ask_then_distinct_stage_ask_routes_through_engine() -> None:
    sheet = CRM_PIPELINE_DRIFT.answer_sheet
    script = OperatorScript.from_components(
        CRM_PIPELINE_DRIFT.persona,
        sheet,
        turns=(
            sheet.opening_message,
            "Please continue.",
            "Please continue again.",
            "Please finish.",
        ),
        turn_budget=4,
        phase_by_turn={1: 1, 2: 2, 3: 3, 4: 4},
    )
    mixed_ask = "Should I make a new workflow to handle the stage?"
    stage_ask = "How should I treat the out-of-list stage?"
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="What is the source?"),
            TurnResult(agent_message=mixed_ask),
            TurnResult(agent_message=stage_ask),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    engine = OperatorEngine(script, transport)
    engine.activate_decision_overlay("crm_deals_v2")

    result = engine.run()

    assert result.turns[1].match.decision_id == "workflow_revision"
    assert result.turns[2].match.decision_id == "new_stage_consequence"
    assert result.turns[2].selected_decision_stage == 1
    assert transport.message_texts[2] == sheet.decision_answers["workflow_revision"].answer
    assert transport.message_texts[3] == sheet.decision_answers["new_stage_consequence"].stages[0]
