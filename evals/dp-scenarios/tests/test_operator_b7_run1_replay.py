"""B7 run-1 routing replay, with tool output and business values removed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.matcher import Category, MatcherBank
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult
from dp_scenarios.scenario import load_scenario

ROOT = Path(__file__).parents[1]
SCENARIOS = ROOT / "scenarios"
FIXTURE = json.loads(
    (ROOT / "tests/fixtures/operator-b7-run1-replay.json").read_text(encoding="utf-8")
)


def _b7():
    return load_scenario(SCENARIOS / "mrr-waterfall")


def test_b7_run1_first_card_unlocks_the_asked_decision_only_after_delivery() -> None:
    scenario = _b7()
    sheet = scenario.answer_sheet
    bank = MatcherBank(scenario.persona, sheet)
    question = FIXTURE["turn_4_same_month_choice"]

    before = bank.reply_for(question)
    assert before.decision_id is None
    assert sheet.decision_answers["same_month_classification"].answer != before.reply

    script = OperatorScript.from_components(
        scenario.persona,
        sheet,
        events=scenario.events,
        turns=sheet.turns[:8],
        turn_budget=8,
        phase_by_turn={turn: scenario.phase_map[turn] for turn in range(1, 9)},
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Which source file should I use?"),
            TurnResult(agent_message="I will inspect the input."),
            TurnResult(agent_message="The definition is in progress."),
            TurnResult(agent_message=question),
            TurnResult(agent_message="I will use your ruling in the definition."),
            TurnResult(agent_message="I will prepare the plan."),
            TurnResult(agent_message=FIXTURE["turn_7_empty_movement_choice"]),
            TurnResult(agent_message="I will continue."),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert result.turns[3].event_ids == ("B7-same-month",)
    assert transport.message_texts[4] == sheet.decision_answers[
        "same_month_classification"
    ].answer
    assert result.turns[4].delivered_decision_id == "same_month_classification"
    assert transport.message_texts[7] == sheet.decision_answers["empty_movement_rows"].answer


def test_b7_run1_plan_approval_and_review_disposition_are_distinct() -> None:
    scenario = _b7()
    bank = MatcherBank(scenario.persona, scenario.answer_sheet)
    negated = FIXTURE["turn_13_no_review"]

    assert not bank.has_review_finding_context(negated)
    plan = bank.reply_for(FIXTURE["turn_21_plan_approval"], context=negated)
    assert plan.category is Category.APPROVAL_REQUEST
    assert plan.decision_id is None

    review = FIXTURE["turn_23_review_choice"]
    assert bank.has_review_finding_context(review)
    for key in ("turn_23_review_choice", "turn_33_review_choice"):
        match = bank.reply_for(FIXTURE[key], context=review)
        assert match.category is Category.DECISION_REQUEST
        assert match.rule_id == "decision.answer.review_fix_authorization"
        assert match.reply == scenario.answer_sheet.decision_answers[
            "review_fix_authorization"
        ].answer


def test_b7_run1_review_choice_replaces_the_next_persona_turn() -> None:
    scenario = _b7()
    script = OperatorScript.from_components(
        scenario.persona,
        scenario.answer_sheet,
        events=scenario.events,
        turns=scenario.answer_sheet.turns[:24],
        turn_budget=24,
        phase_by_turn={turn: scenario.phase_map[turn] for turn in range(1, 25)},
    )
    agent_messages = ["I am continuing the work."] * 24
    agent_messages[12] = FIXTURE["turn_13_no_review"]
    agent_messages[20] = FIXTURE["turn_21_plan_approval"]
    agent_messages[22] = FIXTURE["turn_23_review_choice"]
    transport = InMemoryTransport(
        [TurnResult(agent_message=message) for message in agent_messages]
    )

    result = OperatorEngine(script, transport).run()

    assert result.turns[20].match.decision_id is None
    assert result.turns[22].match.rule_id == "decision.answer.review_fix_authorization"
    assert transport.message_texts[23] == scenario.answer_sheet.decision_answers[
        "review_fix_authorization"
    ].answer


def _publications(*, revised: bool) -> dict[str, object]:
    runs = [("initial-run", "definition-a", 22)]
    if revised:
        runs.append(("revised-run", "definition-b", 40))
    return {
        "run_records": {
            "schema": "dp-scenario-run-records-v1",
            "runs": [
                {
                    "workflow_id": "bridge",
                    "run_id": run,
                    "definition_id": definition,
                    "status_history": [{"turn": turn, "status": "Published"}],
                }
                for run, definition, turn in runs
            ],
        },
        "publication_history": {
            "schema": "dp-scenario-publication-history-v1",
            "releases": [
                {"workflow_id": "bridge", "run_id": run, "definition_id": definition, "turn": 1}
                for run, definition, _ in runs
            ],
        },
    }


def test_b7_publication_cards_wait_for_real_publication_and_then_fire_in_order() -> None:
    schedule = _b7().events
    used = ["B7-same-month"]
    delivered = {"B7-same-month": 4}

    assert schedule.fire(28, used_event_ids=used, delivered_event_turns=delivered) == ()
    for turn, card_id in (
        (28, "B7-spreadsheet-challenge"),
        (29, "B7-billing-contact-request"),
        (30, "B7-E8"),
        (47, "B7-E3"),
    ):
        snapshot = _publications(revised=turn == 47)
        fired = schedule.fire(
            turn,
            run_records=snapshot["run_records"],
            publication_history=snapshot["publication_history"],
            used_event_ids=used,
            delivered_event_turns=delivered,
        )
        assert tuple(card.card_id for card in fired) == (card_id,)
        used.append(card_id)
        delivered[card_id] = turn

    bank = MatcherBank(_b7().persona, _b7().answer_sheet)
    revised = bank.reply_for(
        FIXTURE["turn_4_same_month_choice"], available_event_ids=tuple(used)
    )
    assert revised.decision_id == "same_month_classification_revised"


def test_b7_engine_transmits_all_cards_with_runner_owned_publications() -> None:
    scenario = _b7()
    snapshot = _publications(revised=True)
    result = OperatorEngine(
        scenario.operator_script,
        InMemoryTransport(
            [TurnResult(agent_message="I am continuing the work.") for _ in range(50)]
        ),
        publication_history_reader=lambda: snapshot,
    ).run()

    assert result.fired_event_ids == (
        "B7-same-month",
        "B7-spreadsheet-challenge",
        "B7-billing-contact-request",
        "B7-E8",
        "B7-E3",
    )


@pytest.mark.parametrize(
    "question",
    [
        "The source rows changed. Do you approve this plan?",
        "The spreadsheet has a different total. Should I proceed, yes or no?",
    ],
)
def test_p3_source_challenge_does_not_answer_an_explicit_approval(question: str) -> None:
    scenario = _b7()
    match = MatcherBank(scenario.persona, scenario.answer_sheet).reply_for(question)

    assert match.category is Category.APPROVAL_REQUEST
    assert match.rule_id != "persona.source_question"
    assert match.rule_id != "persona.status_query"


def test_e8_makes_the_revised_same_month_decision_deliverable_once_genuinely_asked() -> None:
    """Defect 2 (r407): the declared ``same_month_classification_revised``
    decision is delivered through the same solicited-exchange mechanism as
    the initial decision, once B7-E8 has fired -- design-B7.md's "Answer
    matching and disclosure" section stages the revised answer until E8
    fires and requires a genuine later exchange, matching the same "within
    the same month"/"both directions" vocabulary used for the initial ask.
    In r407, this decision was never recorded as delivered (turns 42-50)
    only because the run-global reapproval budget (see
    test_operator_revision_reapproval.py) starved every v3 approval ask
    before the agent ever reached a turn that could ask this; the mechanism
    itself, once reachable, already answers it correctly and generically.
    """

    scenario = _b7()
    sheet = scenario.answer_sheet
    bank = MatcherBank(scenario.persona, sheet)
    question = FIXTURE["r407_style_post_e8_same_month_ask"]

    before = bank.reply_for(question, available_event_ids=("B7-same-month",))
    assert before.decision_id == "same_month_classification"
    assert before.reply == sheet.decision_answers["same_month_classification"].answer

    after = bank.reply_for(question, available_event_ids=("B7-same-month", "B7-E8"))
    assert after.decision_id == "same_month_classification_revised"
    assert after.reply == sheet.decision_answers["same_month_classification_revised"].answer

    # End to end: the engine actually delivers it on the next turn once B7-E8
    # has fired, exactly like the initial decision does in
    # ``test_b7_run1_first_card_unlocks_the_asked_decision_only_after_delivery``.
    script = OperatorScript.from_components(
        scenario.persona,
        sheet,
        events=scenario.events,
        turns=sheet.turns[:32],
        turn_budget=32,
        phase_by_turn={turn: scenario.phase_map[turn] for turn in range(1, 33)},
    )
    agent_messages = ["I am continuing the work."] * 32
    agent_messages[3] = FIXTURE["turn_4_same_month_choice"]
    agent_messages[6] = FIXTURE["turn_7_empty_movement_choice"]
    agent_messages[30] = question
    transport = InMemoryTransport(
        [TurnResult(agent_message=message) for message in agent_messages]
    )

    snapshot = _publications(revised=False)
    result = OperatorEngine(
        script, transport, publication_history_reader=lambda: snapshot
    ).run()

    assert "B7-E8" in result.fired_event_ids
    e8_turn = next(
        turn.turn for turn in result.turns if "B7-E8" in turn.event_ids
    )
    assert e8_turn <= 31
    assert result.turns[30].match.decision_id == "same_month_classification_revised"
    assert transport.message_texts[31] == sheet.decision_answers[
        "same_month_classification_revised"
    ].answer
    assert result.turns[31].delivered_decision_id == "same_month_classification_revised"


def test_r407_turn19_dedup_key_choice_is_a_distinct_undeclared_choice_not_event_deduplication() -> None:
    """The "option 2/3" ask at r407 turns 19-21 is a live, improvised choice
    about a structural-validation workaround (landing the raw events export
    as its own model), not a restatement of the declared
    ``event_deduplication`` ruling (which was already answered earlier, via
    the B7-same-month beat). It correctly does not match
    ``decision.answer.event_deduplication`` -- PR #409's undeclared-choice
    handling answers it instead, so the operator still gives an unambiguous
    reply rather than silently dropping it or misrouting it to caveat/source
    vocabulary as it did before #409.
    """

    scenario = _b7()
    bank = MatcherBank(scenario.persona, scenario.answer_sheet)

    for key in ("r407_turn19_dedup_key_choice", "r407_turn21_dedup_key_choice"):
        match = bank.reply_for(FIXTURE[key], available_event_ids=("B7-same-month",))
        assert match.decision_id != "event_deduplication"
        assert match.rule_id != "decision.answer.event_deduplication"
        # It is still recognised as something the agent is asking the
        # operator to resolve, and gets a real (non-empty) answer.
        assert match.solicits_operator is True
        assert match.reply


@pytest.mark.parametrize("scenario_id", ["finance-close", "marketing-attribution", "inventory-position"])
def test_other_scenarios_keep_persona_source_and_approval_routes(scenario_id: str) -> None:
    scenario = load_scenario(SCENARIOS / scenario_id)
    bank = MatcherBank(scenario.persona, scenario.answer_sheet)

    source = bank.reply_for("Which source contains the records?")
    approval = bank.reply_for("Do you approve the plan?")

    assert source.category is Category.SOURCE_QUESTION
    assert source.rule_id == "source.answer.source"
    assert approval.category is Category.APPROVAL_REQUEST
    assert approval.rule_id == "persona.approval_request"
    assert approval.reply == scenario.persona.replies_for("approval_request")[0]
