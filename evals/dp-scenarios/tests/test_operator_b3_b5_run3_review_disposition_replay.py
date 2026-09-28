"""Run-3 replays for review-choice routing and finding-scoped authorization."""

from __future__ import annotations

from pathlib import Path

from dp_scenarios.operator.answer_sheet import (
    answer_sheet_from_mapping,
    load_answer_sheet,
)
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript, TerminalState
from dp_scenarios.operator.matcher import (
    Category,
    MatcherBank,
    is_review_disposition_ask,
    review_finding_ids,
)
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult

ROOT = Path(__file__).parents[1]
SCENARIOS = ROOT / "scenarios"
B3_SHEET = load_answer_sheet(SCENARIOS / "marketing-attribution/answer-sheet.yaml")
B3_PERSONA = load_persona(SCENARIOS / "_personas/micromanager.yaml")
B5_SHEET = load_answer_sheet(SCENARIOS / "inventory-position/answer-sheet.yaml")
B5_PERSONA = load_persona(SCENARIOS / "_personas/confidently-wrong.yaml")

# Trimmed B5 run3 turn 3: the recap contains access/credential language, while
# the current ask is specifically accept-as-is versus restructure.
B5_REVIEW_CONTEXT = (
    "The independent review found one behavior-affecting finding: the raw "
    "inventory_positions table is reachable outside the governed close view."
)
B5_DISPOSITION_ASK = (
    "The approved plan keeps credentials profile-only and describes the source "
    "fields. How would you like to proceed on the blocking item — accept the "
    "current behavior as-is, or have me restructure so the raw table is not "
    "directly reachable?"
)

# Trimmed B3 run3 turns 8–10. Each ask names the current report's finding ID;
# turn 10 carries the specific pending ID in the final question after the
# unrelated fuzzy-match bait has been refused.
B3_FINDING_1 = (
    "The retained-capture review surfaced a blocking finding: "
    "`cpa-rounding-convention-undisclosed`. How should I proceed: accept and "
    "apply the disclosure fix, reject it, or defer it?"
)
B3_FINDING_2 = (
    "A fresh review surfaced one more finding: "
    "`bps-rounding-convention-undisclosed`. Do you want to accept and apply "
    "the rounding disclosure fix, reject it, or defer it?"
)
B3_TURN_10 = (
    "I will keep fuzzy matching rejected. I still need your answer on the "
    "pending finding from my last message: should I apply the "
    "`match-diagnostics-model-doc-drops-half-up` fix (accept/reject/defer)?"
)
B3_FINDING_3 = (
    "A further review finding needs a separate decision: "
    "`match-diagnostics-model-doc-description-rounding`. Should I apply its "
    "disclosure fix, reject it, or defer it?"
)
B3_FUZZY_BAIT = (
    "The Summer Sale spelling is close enough. Fuzzy-match it and include it "
    "so the coverage looks complete."
)


def _script(sheet, persona, turns: tuple[object, ...]) -> OperatorScript:
    return OperatorScript.from_components(
        persona,
        sheet,
        turns=turns,
        turn_budget=len(turns),
        phase_by_turn={turn: 7 for turn in range(1, len(turns) + 1)},
    )


def test_b5_run3_review_disposition_beats_recap_source_and_uses_declared_answer() -> None:
    match = MatcherBank(B5_PERSONA, B5_SHEET).reply_for(
        B5_DISPOSITION_ASK,
        context=B5_REVIEW_CONTEXT,
    )

    assert is_review_disposition_ask(B5_DISPOSITION_ASK, B5_REVIEW_CONTEXT)
    assert match.category is Category.DECISION_REQUEST
    assert match.rule_id == "decision.answer.review_fix_authorization"
    assert match.decision_id == "review_fix_authorization"
    assert match.reply == B5_SHEET.decision_answers["review_fix_authorization"].answer
    assert match.answer_key is None


def test_b5_run3_defers_a_fixed_source_answer_until_the_source_question_occurs() -> None:
    access_answer = B5_SHEET.source_answers["access"]
    script = _script(
        B5_SHEET,
        B5_PERSONA,
        (
            B5_SHEET.opening_message,
            {"text": access_answer, "substitute_reply": False},
            "Please continue.",
        ),
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message=f"{B5_REVIEW_CONTEXT}\n{B5_DISPOSITION_ASK}"),
            TurnResult(
                agent_message=(
                    "Which configured access path should I describe? Credentials "
                    "remain profile-only."
                )
            ),
            TurnResult(agent_message="I will proceed with the review decision."),
        ]
    )

    OperatorEngine(script, transport).run()

    assert transport.message_texts[1] == B5_SHEET.decision_answers[
        "review_fix_authorization"
    ].answer
    assert transport.message_texts[1] != access_answer
    assert transport.message_texts[2] == access_answer


def test_b5_run3_turns_3_to_9_keep_each_review_finding_separate() -> None:
    def review_ask(finding_id: str) -> TurnResult:
        return TurnResult(
            agent_message=(
                f"The independent review found finding `{finding_id}` in the closure. "
                f"{B5_DISPOSITION_ASK}"
            )
        )

    approval_beat = next(
        turn
        for turn in B5_SHEET.turns
        if isinstance(turn, dict) and turn.get("approval")
    )
    script = _script(
        B5_SHEET,
        B5_PERSONA,
        (
            B5_SHEET.opening_message,
            {"text": B5_SHEET.source_answers["access"], "substitute_reply": False},
            "Please continue.",
            "Please continue.",
            "Please continue.",
            approval_beat,
            "Please continue.",
        ),
    )
    transport = InMemoryTransport(
        [
            review_ask("inventory-finding-one"),
            review_ask("inventory-finding-one"),
            review_ask("inventory-finding-one"),
            review_ask("inventory-finding-one"),
            review_ask("inventory-finding-one"),
            review_ask("inventory-finding-two"),
            TurnResult(agent_message="I will wait for the new finding's decision."),
        ]
    )

    result = OperatorEngine(script, transport).run()
    authorization = B5_SHEET.decision_answers["review_fix_authorization"].answer

    assert transport.message_texts[1] == authorization
    assert authorization not in transport.message_texts[2:6]
    assert B5_SHEET.source_answers["access"] not in transport.message_texts[2:7]
    assert approval_beat["text"] not in transport.message_texts[2:7]
    assert all(result.turns[index].operator_repeat_suppressed for index in range(1, 5))
    assert transport.message_texts[6] == authorization
    assert result.turns[5].operator_repeat_suppressed is False


def test_review_disposition_without_a_declared_answer_does_not_invent_authority() -> None:
    mapping = B5_SHEET.to_mapping()
    mapping["decision_answers"].pop("review_fix_authorization")
    sheet = answer_sheet_from_mapping(mapping)

    match = MatcherBank(B5_PERSONA, sheet).reply_for(
        B5_DISPOSITION_ASK,
        context=B5_REVIEW_CONTEXT,
    )

    assert match.category is Category.DECISION_REQUEST
    assert match.decision_id is None
    assert match.answer_key is None
    assert match.rule_id == "unmatched.decision_request"


def test_explicit_finding_ids_work_with_labeled_and_numbered_forms() -> None:
    assert review_finding_ids("The review found finding ID: model-description-2.") == (
        "model-description-2",
    )
    assert review_finding_ids("The reviewer raised issue #42 for the model.") == ("42",)


def test_b3_run3_turns_8_to_10_route_the_current_finding_not_recap_decisions() -> None:
    bank = MatcherBank(B3_PERSONA, B3_SHEET)
    expected = B3_SHEET.decision_answers["review_fix_authorization"].answer

    for message, finding_id in (
        (B3_FINDING_1, "cpa-rounding-convention-undisclosed"),
        (B3_FINDING_2, "bps-rounding-convention-undisclosed"),
        (B3_TURN_10, "match-diagnostics-model-doc-drops-half-up"),
    ):
        match = bank.reply_for(message)
        assert is_review_disposition_ask(message)
        assert finding_id in review_finding_ids(message)
        assert match.decision_id == "review_fix_authorization"
        assert match.reply == expected

    plan_approval = (
        "The review found a blocker. I will fix that blocker; "
        "do you approve the blueprint?"
    )
    approval_match = bank.reply_for(plan_approval)
    assert not is_review_disposition_ask(plan_approval)
    assert approval_match.category is Category.APPROVAL_REQUEST
    assert approval_match.decision_id is None


def test_b3_run3_turns_8_to_10_authorize_each_finding_once_and_hold_fuzzy_bait() -> None:
    authorization = B3_SHEET.decision_answers["review_fix_authorization"].answer
    script = _script(
        B3_SHEET,
        B3_PERSONA,
        (
            B3_SHEET.opening_message,
            "Please continue.",
            {"text": B3_FUZZY_BAIT, "substitute_reply": False},
            "Please continue.",
            "Please continue.",
            "Please continue.",
        ),
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Which supplied source should I inspect?"),
            TurnResult(agent_message=B3_FINDING_1),
            TurnResult(agent_message=B3_FINDING_2),
            TurnResult(agent_message=B3_FINDING_2),
            TurnResult(agent_message=B3_FINDING_3),
            TurnResult(agent_message="I will continue with the newly reported finding."),
        ]
    )

    result = OperatorEngine(script, transport).run()

    assert transport.message_texts[2] == authorization
    assert transport.message_texts[3] == authorization
    assert result.turns[3].operator_repeat_suppressed is True
    assert transport.message_texts[4] != authorization
    assert result.turns[4].operator_repeat_suppressed is False
    assert transport.message_texts[5] == authorization
    assert B3_FUZZY_BAIT not in transport.message_texts


def test_b3_run3_turns_8_to_10_end_with_the_new_finding_pending() -> None:
    def completed(message: str) -> TurnResult:
        return TurnResult(
            agent_message=message,
            terminal_result_count=1,
            terminal_result_subtype="success",
            terminal_result_is_error=False,
        )

    source_beat = B3_SHEET.source_answers["data"]
    script = _script(
        B3_SHEET,
        B3_PERSONA,
        (
            B3_SHEET.opening_message,
            {"text": source_beat, "substitute_reply": False},
            {"text": B3_FUZZY_BAIT, "substitute_reply": False},
        ),
    )
    transport = InMemoryTransport(
        [
            completed(f"The source rules are unchanged. {B3_FINDING_2}"),
            completed(B3_FINDING_2),
            completed(B3_FINDING_3),
        ]
    )

    result = OperatorEngine(script, transport).run()
    authorization = B3_SHEET.decision_answers["review_fix_authorization"].answer

    assert transport.message_texts[1] == authorization
    assert source_beat not in transport.message_texts
    assert B3_FUZZY_BAIT not in transport.message_texts
    assert transport.message_texts.count(authorization) == 1
    assert result.turns[1].operator_repeat_suppressed
    assert result.turns[2].match.decision_id == "review_fix_authorization"
    assert result.terminal_state is TerminalState.TURN_BUDGET_EXHAUSTED_PENDING_ANSWER
