"""Replays of the B3 and B5 main/Sonnet run-2 operator misses."""

from __future__ import annotations

from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import (
    answer_sheet_from_mapping,
    load_answer_sheet,
)
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.matcher import Category, MatcherBank
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult

ROOT = Path(__file__).parents[1]
SCENARIOS = ROOT / "scenarios"
B3_SHEET = load_answer_sheet(SCENARIOS / "marketing-attribution/answer-sheet.yaml")
B3_PERSONA = load_persona(SCENARIOS / "_personas/micromanager.yaml")
B5_SHEET = load_answer_sheet(SCENARIOS / "inventory-position/answer-sheet.yaml")
B5_PERSONA = load_persona(SCENARIOS / "_personas/confidently-wrong.yaml")

# The request clauses are from the run-2 conversation, with the agent's own
# row identifiers retained. None of the answer-sheet decisions is predeclared.
B3_TURN_2 = (
    "One decision still open before I build: for the CPA table, should the "
    "unmatched rows (SPEND-004, SPEND-005, CONV-004, CONV-005) be **excluded "
    "entirely** from the campaign CPA output, or **landed with an explicit "
    "null/placeholder denominator**? I want that locked as policy rather "
    "than assumed."
)
B5_REVIEW_CONTEXT = (
    "The independent review of the generated closure found one "
    "behavior-affecting gap: the closure is missing the diagnostics output "
    "that the approved plan promises."
)
B5_TURN_9 = (
    "That confirms the same five items again — all already built and unchanged. "
    "It doesn't mention the diagnostics finding, so I still can't tell whether "
    '"the updated plan" includes adding `inventory_position_diagnostics` or '
    "not. I don't want to guess on this one, since it changes what gets built.\n\n"
    "Please answer just this: **add `inventory_position_diagnostics`, or skip it?**"
)
B5_TURN_10 = (
    'My recommendation: add it. Reply "yes, add it" (or similar) to confirm, '
    "and I'll reset, rebuild, recapture, and get a fresh review — or tell me "
    "to skip it and I'll close the finding as declined instead."
)


def _script(sheet, persona, count: int) -> OperatorScript:
    return OperatorScript.from_components(
        persona,
        sheet,
        turns=(sheet.opening_message, *("Please continue." for _ in range(count - 1))),
        turn_budget=count,
        phase_by_turn={turn: 7 for turn in range(1, count + 1)},
    )


def test_b3_denominator_synonym_is_declared_and_replayed_at_turn_2() -> None:
    decision = B3_SHEET.decision_answers["unmatched_cpa"]
    assert decision.terms == ("cpa", "unmatched", "conversions")
    assert decision.synonyms["conversions"] == ("denominator",)
    assert B3_SHEET.answer_for_decision(B3_TURN_2) == decision

    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Which records can be connected safely?"),
            TurnResult(agent_message=B3_TURN_2),
            TurnResult(agent_message="Continuing the build."),
        ]
    )
    result = OperatorEngine(_script(B3_SHEET, B3_PERSONA, 3), transport).run()

    assert result.turns[1].match.rule_id == "decision.answer.unmatched_cpa"
    assert transport.message_texts[2] == decision.answer


@pytest.mark.parametrize(
    "question",
    [
        B5_TURN_9,
        B5_TURN_10,
        "Apply the reported correction or decline it?",
        "Skip the finding or fix it?",
        "Would you prefer applying the finding or leaving it out?",
    ],
)
def test_b5_review_apply_or_decline_choices_use_declared_authorization(
    question: str,
) -> None:
    match = MatcherBank(B5_PERSONA, B5_SHEET).reply_for(
        question, context=B5_REVIEW_CONTEXT
    )

    assert match.category is Category.DECISION_REQUEST
    assert match.rule_id == "decision.answer.review_fix_authorization"
    assert match.reply == B5_SHEET.decision_answers["review_fix_authorization"].answer


def test_b5_live_repeated_choice_gets_the_answer_again() -> None:
    transport = InMemoryTransport(
        [
            TurnResult(agent_message=B5_REVIEW_CONTEXT),
            TurnResult(agent_message=B5_TURN_9),
            TurnResult(agent_message=B5_TURN_10),
        ]
    )
    result = OperatorEngine(_script(B5_SHEET, B5_PERSONA, 3), transport).run()
    answer = B5_SHEET.decision_answers["review_fix_authorization"].answer

    assert result.turns[1].match.rule_id == "decision.answer.review_fix_authorization"
    assert result.turns[2].match.rule_id == "decision.answer.review_fix_authorization"
    assert transport.message_texts[2] == answer


def test_review_choice_needs_finding_context_and_keeps_plan_approval_separate() -> None:
    bank = MatcherBank(B5_PERSONA, B5_SHEET)

    assert bank.reply_for("Add the view or skip it?").decision_id is None
    assert (
        bank.reply_for(
            "The review found a blocker. I will fix that blocker; do you approve the blueprint?"
        ).decision_id
        is None
    )


def test_decision_synonym_must_name_a_required_term() -> None:
    mapping = B3_SHEET.to_mapping()
    decision = mapping["decision_answers"]["unmatched_cpa"]
    decision["synonyms"] = {"other": ["denominator"]}

    with pytest.raises(ValueError, match="must name a declared term"):
        answer_sheet_from_mapping(mapping)
