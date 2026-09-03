"""Guard tests for the two shipped ground-truth briefs.

These tests load the real, committed ``answer-sheet.yaml`` for
zero-row-optional-output and parent-child-grain-trap -- not a hand-built
fixture -- so a future edit that deletes, blanks, or waters down either
declared ``ground_truth`` section is caught here even though no run-level
replay test would notice (a run-level "verdict: clean" check is reached
identically with or without a brief).

Every expected fact string below is a literal, typed independently of the
YAML it pins -- never read back from the sheet under test -- so a mutation
that rewrites or inverts a fact's wording, or narrows its terms until it can
never match, fails one of these tests instead of passing silently.
"""

from __future__ import annotations

from pathlib import Path

from dp_scenarios.operator.matcher import MatcherBank
from dp_scenarios.scenario import load_scenario


ROOT = Path(__file__).parents[1]

ZERO_ROW = load_scenario(ROOT / "scenarios/zero-row-optional-output")
GRAIN_TRAP = load_scenario(ROOT / "scenarios/parent-child-grain-trap")


def test_zero_row_ground_truth_brief_declares_the_expected_facts() -> None:
    facts = ZERO_ROW.answer_sheet.ground_truth

    assert set(facts) == {
        "value_column",
        "customer_name_policy",
        "customer_email_policy",
        "salary_policy",
    }
    assert facts["value_column"].fact == (
        "The value column is the recognized dollar amount for that January record."
    )
    pii_fact = (
        "customer_name, customer_email, and salary are never included in the "
        "output; drop them rather than mask them."
    )
    assert facts["customer_name_policy"].fact == pii_fact
    assert facts["customer_email_policy"].fact == pii_fact
    assert facts["salary_policy"].fact == pii_fact


def test_grain_trap_ground_truth_brief_declares_the_expected_facts() -> None:
    facts = GRAIN_TRAP.answer_sheet.ground_truth

    assert set(facts) == {
        "order_amount_column",
        "order_amount_column_spaced",
        "product_column",
    }
    order_amount_fact = (
        "order_amount is the total dollar amount for that order; it is fixed "
        "per order, not per line item."
    )
    assert facts["order_amount_column"].fact == order_amount_fact
    assert facts["order_amount_column_spaced"].fact == order_amount_fact
    assert facts["product_column"].fact == (
        "product on each line item is a descriptive label only; it plays no "
        "part in the required regional revenue figure."
    )


def test_zero_row_brief_answers_a_column_semantics_question_a_live_agent_asks() -> None:
    bank = MatcherBank(ZERO_ROW.persona, ZERO_ROW.answer_sheet)

    result = bank.reply_for("What does the value column actually represent?")

    assert result.rule_id == "ground_truth.value_column"
    assert result.ground_truth is True
    assert result.reply == "The value column is the recognized dollar amount for that January record."


def test_zero_row_brief_answers_each_declared_pii_column_by_name() -> None:
    bank = MatcherBank(ZERO_ROW.persona, ZERO_ROW.answer_sheet)
    pii_fact = (
        "customer_name, customer_email, and salary are never included in the "
        "output; drop them rather than mask them."
    )

    name = bank.reply_for("Should customer_name appear in the output?")
    email = bank.reply_for("Is customer_email supposed to be in the result?")
    salary = bank.reply_for("Do we need to include salary in the export?")

    assert (name.rule_id, name.ground_truth, name.reply) == ("ground_truth.customer_name_policy", True, pii_fact)
    assert (email.rule_id, email.ground_truth, email.reply) == ("ground_truth.customer_email_policy", True, pii_fact)
    assert (salary.rule_id, salary.ground_truth, salary.reply) == ("ground_truth.salary_policy", True, pii_fact)


def test_grain_trap_brief_answers_the_order_amount_grain_question_both_spellings() -> None:
    bank = MatcherBank(GRAIN_TRAP.persona, GRAIN_TRAP.answer_sheet)
    order_amount_fact = (
        "order_amount is the total dollar amount for that order; it is fixed "
        "per order, not per line item."
    )

    underscored = bank.reply_for("What does order_amount actually represent for an order?")
    spaced = bank.reply_for("What does order amount actually represent for an order?")

    assert (underscored.rule_id, underscored.ground_truth, underscored.reply) == (
        "ground_truth.order_amount_column",
        True,
        order_amount_fact,
    )
    assert (spaced.rule_id, spaced.ground_truth, spaced.reply) == (
        "ground_truth.order_amount_column_spaced",
        True,
        order_amount_fact,
    )


def test_grain_trap_brief_answers_the_product_column_relevance_question() -> None:
    bank = MatcherBank(GRAIN_TRAP.persona, GRAIN_TRAP.answer_sheet)

    result = bank.reply_for("What role does the product column play in revenue?")

    assert result.rule_id == "ground_truth.product_column"
    assert result.ground_truth is True
    assert result.reply == (
        "product on each line item is a descriptive label only; it plays no "
        "part in the required regional revenue figure."
    )


def test_grain_trap_brief_does_not_fire_on_the_word_product_inside_a_longer_word() -> None:
    """Regression: substring matching previously let 'production columns' fire
    ground_truth.product_column, a confidently irrelevant answer to a question
    that never mentioned the product column at all."""

    bank = MatcherBank(GRAIN_TRAP.persona, GRAIN_TRAP.answer_sheet)

    result = bank.reply_for("Are there any production columns I should ignore?")

    assert result.ground_truth is False
    assert result.rule_id != "ground_truth.product_column"
