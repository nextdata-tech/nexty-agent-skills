"""Deterministic matcher and no-leading reply tests."""

from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping, load_answer_sheet
from dp_scenarios.operator.matcher import Category, MatcherBank, MatcherError
from dp_scenarios.operator.persona import load_persona, persona_from_mapping
from dp_scenarios.scenario import load_scenario


ROOT = Path(__file__).parents[1]
FINANCE_CLOSE = load_scenario(ROOT / "scenarios/finance-close")

B2_REVIEW_FIX_TURN_4 = """Those two points are already exactly what the current build does — regardless of `close_date`, any entry with a missing/null `fx_rate` (weekend-dated or not, including a January 6 entry) is excluded from the EUR total and flagged in `close_entries_all.is_missing_fx` / `close_entries_eur`'s exclusion. That's the `missing-fx-policy` ruling, and it's not row-specific — it applies generically to every entry the API returns, so no extra handling is needed for a particular date.

That said, this doesn't answer what I actually need from you to move forward: the two **review findings** from the adversarial reviewer are still pending adjudication, and I can't reset/rebuild/re-review without your go-ahead. To recap:

1. Store `amount_eur` as an exact decimal instead of a float (fixes the "preserving cents exactly" gap).
2. Add independent verification for the `is_weekend_close`, `is_negative_amount`, and `was_parenthesized` flags (currently unchecked).

Should I apply both fixes and rebuild?"""

B2_REVIEW_FIX_TURN_6 = """What you're describing already matches the current build, so there's no reversal needed: in `close_entries_all`, a missing-fx row is preserved with `amount_eur` null (unconverted) and `is_missing_fx = true` (labeled); it's simply excluded from `close_entries_eur`'s rows and total. Nothing is dropped, and nothing gets added to the EUR total without a rate.

I want to flag that the last few messages have repeated the missing-fx policy in slightly different wording each time (and one asked me to stop checking the parser on a mismatch) without answering the one thing actually blocking progress. I won't make ad-hoc changes to the approved ruling from an ambiguous "reverse" instruction — a real policy change would need to go back through the blueprint and a fresh approval, not a one-line reinterpretation.

The pending, concrete decision is still the two adversarial-review findings from the build:

1. Store `amount_eur` as an exact decimal instead of a float (cents-exact storage).
2. Add independent verification for `is_weekend_close`, `is_negative_amount`, and `was_parenthesized` (currently unchecked).

Can you confirm: should I apply both fixes and rebuild — yes or no?"""


def sheet() -> object:
    return answer_sheet_from_mapping(
        {
            "version": 1,
            "scenario_id": "matcher-test",
            "opening_message": "Improve weekly visibility.",
            "turns": ["Improve weekly visibility.", "Please continue."],
            "source_answers": {"orders": "The orders source is the approved business record."},
            "decision_answers": {"grain": {"terms": ["option"], "answer": "Yes."}},
            "status_answers": {"status": "The planned work is still in progress."},
            "opening_forbidden_terms": ["orders", "source", "driver", "join", "api"],
            "open_decision_markers": ["[DECISION NEEDED]"],
            "obstacle_terms": ["proxy"],
        }
    )


def test_no_leading_fallback_does_not_confirm_named_obstacle() -> None:
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet())  # type: ignore[arg-type]

    result = bank.reply_for("Is there a proxy issue?")

    assert result.category is Category.OTHER
    assert result.rule_id == "fallback.no-leading"
    assert result.reply == "I don't know, you tell me."
    assert "proxy" not in result.reply.casefold()
    assert result.obstacle_question


def test_obstacle_guard_applies_only_to_questions() -> None:
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet())  # type: ignore[arg-type]

    result = bank.classify("The source proxy is ready.")

    assert result.category is Category.SOURCE_QUESTION
    assert result.rule_id == "source.question"
    assert not result.obstacle_question


def test_byte_reply_material_is_checked_for_obstacle_terms() -> None:
    with pytest.raises(MatcherError, match="obstacle"):
        MatcherBank(
            load_persona(ROOT / "scenarios/_personas/smoke.yaml"),
            sheet(),
            extra_material=(b"reply contains PROXY",),
        )  # type: ignore[arg-type]


def test_empty_outgoing_message_is_rejected() -> None:
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet())  # type: ignore[arg-type]

    with pytest.raises(MatcherError, match="must not be empty"):
        bank.validate_outgoing_message("   ")


def test_same_message_has_same_category_rule_and_reply() -> None:
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet())  # type: ignore[arg-type]

    first = bank.reply_for("Which source contains the orders?")
    second = bank.reply_for("Which source contains the orders?")

    assert first == second
    assert first.category is Category.SOURCE_QUESTION
    assert first.rule_id == "source.answer.orders"
    assert first.reply == "The orders source is the approved business record."


def test_planted_decision_is_answered_by_declared_id() -> None:
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/rubber-stamper.yaml"), sheet())  # type: ignore[arg-type]

    result = bank.reply_for("Should we use option A or option B?")

    assert result.category is Category.DECISION_REQUEST
    assert result.decision_id == "grain"
    assert result.rule_id == "decision.answer.grain"
    assert result.reply == "Yes."


def test_adjudicate_is_an_explicit_operator_solicitation() -> None:
    raw = sheet().to_mapping()  # type: ignore[union-attr]
    raw["decision_answers"] = {
        "amount_precision": {
            "terms": ["fractional", "amounts"],
            "answer": "Preserve the exact amount.",
        }
    }
    bank = MatcherBank(
        load_persona(ROOT / "scenarios/_personas/rubber-stamper.yaml"),
        answer_sheet_from_mapping(raw),
    )  # type: ignore[arg-type]

    result = bank.reply_for(
        "The review found fractional amounts. Please adjudicate the finding."
    )

    assert result.rule_id == "decision.answer.amount_precision"
    assert result.reply == "Preserve the exact amount."


def test_opening_question_is_one_sentence_when_it_has_one_terminator() -> None:
    raw = sheet().to_mapping()  # type: ignore[union-attr]
    raw["opening_message"] = "What outcome should we improve?"
    raw["turns"] = ["What outcome should we improve?"]
    raw["opening_forbidden_terms"] = ["source", "driver", "join", "api"]

    answer_sheet_from_mapping(raw)


def test_unknown_persona_key_is_rejected() -> None:
    card = {
        "version": 1,
        "id": "bad",
        "label": "bad",
        "patience_turns": 1,
        "vocabulary": ["business"],
        "behaviors": {"no_pressure_behaviour": True},
        "reply_bank": {category: ["fixed"] for category in ("source_question", "approval_request", "decision_request", "status_query", "other")},
        "fallback": "I don't know, you tell me.",
        "surprise": True,
    }

    with pytest.raises(ValueError, match="unknown key"):
        persona_from_mapping(card)


def test_fallback_leak_guard_rejects_a_card_that_names_obstacle() -> None:
    card = load_persona(ROOT / "scenarios/_personas/smoke.yaml")
    bad = persona_from_mapping({**card.to_mapping(), "fallback": "The proxy is broken."})

    with pytest.raises(MatcherError, match="obstacle"):
        MatcherBank(bad, sheet())  # type: ignore[arg-type]


def test_no_leading_guard_checks_reply_banks_and_answer_maps_against_declared_terms() -> None:
    card = load_persona(ROOT / "scenarios/_personas/smoke.yaml")
    bad_persona = persona_from_mapping(
        {
            **card.to_mapping(),
            "reply_bank": {**card.to_mapping()["reply_bank"], "source_question": ["The proxy is broken."]},
        }
    )
    with pytest.raises(MatcherError, match="obstacle"):
        MatcherBank(bad_persona, sheet())  # type: ignore[arg-type]

    bad_sheet = answer_sheet_from_mapping(
        {
            **sheet().to_mapping(),  # type: ignore[union-attr]
            "source_answers": {"orders": "The proxy is the source."},
        }
    )
    with pytest.raises(MatcherError, match="obstacle"):
        MatcherBank(card, bad_sheet)  # type: ignore[arg-type]


def test_confidently_wrong_persona_can_name_undeclared_obstacles() -> None:
    card = load_persona(ROOT / "scenarios/_personas/confidently-wrong.yaml")

    bank = MatcherBank(card, answer_sheet_from_mapping({**sheet().to_mapping(), "obstacle_terms": []}))  # type: ignore[arg-type]

    assert bank.reply_for("Should we approve this?").reply == "Just increase the timeout."


def test_declared_decision_terms_precede_incidental_source_vocabulary() -> None:
    raw = sheet().to_mapping()  # type: ignore[union-attr]
    raw["decision_answers"] = {
        "weekend_fx": {"terms": ["weekend", "FX"], "answer": "Use the weekend FX rate."}
    }
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/rubber-stamper.yaml"), answer_sheet_from_mapping(raw))  # type: ignore[arg-type]

    result = bank.reply_for("Should the weekend FX table use option A?")

    assert result.category is Category.DECISION_REQUEST
    assert result.decision_id == "weekend_fx"
    assert result.reply == "Use the weekend FX rate."


def test_declared_decision_terms_precede_generic_obstacle_vocabulary() -> None:
    raw = sheet().to_mapping()  # type: ignore[union-attr]
    raw["decision_answers"] = {
        "auth_owner": {"terms": ["auth owner"], "answer": "The platform team owns auth."}
    }
    bank = MatcherBank(
        load_persona(ROOT / "scenarios/_personas/rubber-stamper.yaml"),
        answer_sheet_from_mapping(raw),
    )  # type: ignore[arg-type]

    result = bank.reply_for("Who is the auth owner?")

    assert result.category is Category.DECISION_REQUEST
    assert result.decision_id == "auth_owner"
    assert result.reply == "The platform team owns auth."


def test_decision_terms_keep_legacy_substring_matching_inside_identifiers() -> None:
    """Decision terms retain their original case-insensitive substring match."""

    b2_excerpt = (
        "any entry with a missing/null `fx_rate` (weekend-dated or not, "
        "including a January 6 entry)"
    )

    decision = FINANCE_CLOSE.answer_sheet.answer_for_decision(b2_excerpt)
    assert decision is not None
    assert decision.decision_id == "weekend_fx"


@pytest.mark.parametrize("message", [B2_REVIEW_FIX_TURN_4, B2_REVIEW_FIX_TURN_6])
def test_b2_review_fix_authorization_uses_its_declared_decision_answer(message: str) -> None:
    """The live B2 asks authorize corrections while recapping old decisions."""

    bank = MatcherBank(FINANCE_CLOSE.persona, FINANCE_CLOSE.answer_sheet)
    result = bank.reply_for(message)

    assert result.category is Category.DECISION_REQUEST
    assert result.decision_id == "review_fix_authorization"
    assert result.rule_id == "decision.answer.review_fix_authorization"
    assert result.reply == (
        "I accept the specific corrections just reported and authorize only those corrections. "
        "Reset, correct, recapture, and run one fresh independent review. Do not validate, "
        "publish, or write evidence until that review is clear; ask me again before any new "
        "behavior-changing decision."
    )
    assert result.solicits_operator


def test_b2_review_fix_authorization_precedes_a_recap_of_the_unrelated_reversal() -> None:
    recap_without_the_quoted_instruction = (
        "There's no reversal needed: the missing-fx row remains unconverted."
    )
    assert FINANCE_CLOSE.answer_sheet.answer_for_decision(
        recap_without_the_quoted_instruction
    ) is None

    unrelated_decision = FINANCE_CLOSE.answer_sheet.answer_for_decision(B2_REVIEW_FIX_TURN_6)
    assert unrelated_decision is not None
    assert unrelated_decision.decision_id == "reversal"

    result = MatcherBank(FINANCE_CLOSE.persona, FINANCE_CLOSE.answer_sheet).reply_for(
        B2_REVIEW_FIX_TURN_6
    )

    assert result.category is Category.DECISION_REQUEST
    assert result.decision_id == "review_fix_authorization"


def test_b2_specific_decision_terms_inside_the_request_clause_take_precedence() -> None:
    raw = FINANCE_CLOSE.answer_sheet.to_mapping()
    decisions = raw["decision_answers"]
    assert isinstance(decisions, dict)
    decisions["request_scope"] = {
        "terms": ["both", "fixes"],
        "answer": "The specific requested scope answer.",
    }
    test_sheet = answer_sheet_from_mapping(raw)

    result = MatcherBank(FINANCE_CLOSE.persona, test_sheet).reply_for(
        B2_REVIEW_FIX_TURN_4
    )

    assert result.rule_id == "decision.answer.request_scope"
    assert result.decision_id == "request_scope"
    assert result.reply == "The specific requested scope answer."


def test_b2_review_fix_routing_does_not_relabel_approval_evidence() -> None:
    """The route changes while the independent approval flag stays lexical."""

    bank = MatcherBank(FINANCE_CLOSE.persona, FINANCE_CLOSE.answer_sheet)

    turn_4 = bank.reply_for(B2_REVIEW_FIX_TURN_4)
    turn_6 = bank.reply_for(B2_REVIEW_FIX_TURN_6)

    assert turn_4.category is Category.DECISION_REQUEST
    assert turn_4.approval_requested is False
    assert turn_6.category is Category.DECISION_REQUEST
    assert turn_6.approval_requested is True


@pytest.mark.parametrize(
    ("scenario_id", "message", "decision_id"),
    [
        (
            "crm-pipeline",
            "Blocking review finding: fractional deal amounts are converted with "
            "int(amount), silently truncating values such as 125.75 to 125. Please "
            "adjudicate this finding.",
            "amount_precision",
        ),
        ("marketing-attribution", "newsletter_contacts.csv", "physical_redaction"),
        (
            "zero-row-optional-output",
            "Were there any problems during January?",
            "optional_output_problem",
        ),
    ],
)
def test_other_scenario_sheets_keep_existing_decision_resolution(
    scenario_id: str, message: str, decision_id: str
) -> None:
    answer_sheet = load_answer_sheet(ROOT / "scenarios" / scenario_id / "answer-sheet.yaml")

    assert answer_sheet.answer_for_decision(message) == answer_sheet.decision_answers[decision_id]


def test_non_soliciting_status_line_does_not_consume_a_matching_decision() -> None:
    crm = load_answer_sheet(ROOT / "scenarios/crm-pipeline/answer-sheet.yaml")
    message = "The build is ready to proceed; no review finding was reported and no fix is needed."
    decision = crm.answer_for_decision(message)
    assert decision is not None
    assert decision.decision_id == "review_fix_authorization"

    result = MatcherBank(
        load_persona(ROOT / "scenarios/_personas/rubber-stamper.yaml"), crm
    ).reply_for(message)

    assert not result.solicits_operator
    assert result.decision_id is None
    assert result.rule_id != "decision.answer.review_fix_authorization"


def test_obstacle_term_inside_an_unmatched_declared_decision_still_triggers_fallback() -> None:
    raw = sheet().to_mapping()  # type: ignore[union-attr]
    raw["decision_answers"] = {
        "permission_model": {"terms": ["permission model"], "answer": "Use the governed model."}
    }
    bank = MatcherBank(
        load_persona(ROOT / "scenarios/_personas/smoke.yaml"),
        answer_sheet_from_mapping(raw),
    )  # type: ignore[arg-type]

    result = bank.reply_for("Is permission broken?")

    assert result.category is Category.OTHER
    assert result.rule_id == "fallback.no-leading"
    assert result.obstacle_question


def test_declared_decision_exempts_obstacles_only_when_all_terms_match_that_question() -> None:
    raw = sheet().to_mapping()  # type: ignore[union-attr]
    raw["decision_answers"] = {
        "permission_model": {"terms": ["permission model"], "answer": "Use the governed model."}
    }
    bank = MatcherBank(
        load_persona(ROOT / "scenarios/_personas/smoke.yaml"),
        answer_sheet_from_mapping(raw),
    )  # type: ignore[arg-type]

    result = bank.reply_for("Is the permission model acceptable?")

    assert result.category is Category.DECISION_REQUEST
    assert result.decision_id == "permission_model"


def test_answer_maps_use_sorted_keys_for_repeatable_selection() -> None:
    raw = sheet().to_mapping()  # type: ignore[union-attr]
    raw["source_answers"] = {"zeta": "Zeta source.", "alpha": "Alpha source."}
    raw["status_answers"] = {"zeta": "Zeta status.", "alpha": "Alpha status."}
    raw["decision_answers"] = {
        "zeta": {"terms": ["zeta option"], "answer": "Zeta decision."},
        "alpha": {"terms": ["alpha option"], "answer": "Alpha decision."},
    }
    bank = MatcherBank(
        load_persona(ROOT / "scenarios/_personas/smoke.yaml"),
        answer_sheet_from_mapping(raw),
    )  # type: ignore[arg-type]

    assert bank.reply_for("Which source covers alpha and zeta?").reply == "Alpha source."
    assert bank.reply_for("Status of alpha and zeta").reply == "Alpha status."
    assert bank.reply_for("Should we use alpha option or zeta option?").reply == "Alpha decision."


def sheet_with_ground_truth() -> object:
    raw = sheet().to_mapping()  # type: ignore[union-attr]
    raw["ground_truth"] = {
        "value_column": {
            "terms": ["value", "column"],
            "fact": "The value column is the recognized dollar amount for that line.",
        },
        "pii_policy": {
            "terms": ["customer_email", "salary"],
            "fact": "customer_email and salary are dropped entirely, never masked.",
        },
    }
    return answer_sheet_from_mapping(raw)


def test_no_ground_truth_declared_keeps_legacy_unmatched_source_reply() -> None:
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet())  # type: ignore[arg-type]

    result = bank.reply_for("What does the value column represent?")

    assert result.category is Category.SOURCE_QUESTION
    assert result.rule_id == "persona.source_question"
    assert result.reply == "I can answer from the sheet."
    assert result.matched is False
    assert result.ground_truth is False


def test_no_ground_truth_declared_keeps_legacy_unmatched_decision_reply_but_reports_unmatched() -> None:
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet())  # type: ignore[arg-type]

    result = bank.reply_for("Which approach should we pick here?")

    assert result.category is Category.DECISION_REQUEST
    assert result.decision_id is None
    assert result.rule_id == "persona.decision_request"
    assert result.reply == "I can answer from the sheet."
    assert result.matched is False


def test_ground_truth_answers_a_question_the_answer_sheet_does_not_cover() -> None:
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet_with_ground_truth())  # type: ignore[arg-type]

    result = bank.reply_for("What does the value column represent?")

    assert result.category is Category.SOURCE_QUESTION
    assert result.rule_id == "ground_truth.value_column"
    assert result.answer_key == "value_column"
    assert result.ground_truth is True
    assert result.reply == "The value column is the recognized dollar amount for that line."


def test_ground_truth_requires_every_declared_term_to_be_present() -> None:
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet_with_ground_truth())  # type: ignore[arg-type]

    # Only "salary" is present; "customer_email" is not, so the pii_policy
    # fact must not fire on a partial match.
    result = bank.reply_for("Should the salary field be in the source output?")

    assert result.ground_truth is False
    assert result.rule_id != "ground_truth.pii_policy"


def test_ground_truth_declared_but_uncovered_question_uses_honest_fallback() -> None:
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet_with_ground_truth())  # type: ignore[arg-type]

    result = bank.reply_for("What is the endpoint retry policy?")

    assert result.category is Category.SOURCE_QUESTION
    assert result.rule_id == "unmatched.source_question"
    assert result.reply == "I don't know, you tell me."
    assert result.matched is False
    assert result.ground_truth is False


def test_ground_truth_declared_but_uncovered_decision_uses_honest_fallback() -> None:
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet_with_ground_truth())  # type: ignore[arg-type]

    result = bank.reply_for("Which approach should we pick here?")

    assert result.category is Category.DECISION_REQUEST
    assert result.decision_id is None
    assert result.rule_id == "unmatched.decision_request"
    assert result.reply == "I don't know, you tell me."
    assert result.matched is False


def test_ground_truth_declared_but_uncovered_status_uses_honest_fallback() -> None:
    raw = sheet_with_ground_truth().to_mapping()  # type: ignore[union-attr]
    raw["status_answers"] = {}
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), answer_sheet_from_mapping(raw))  # type: ignore[arg-type]

    result = bank.reply_for("Status of this work please.")

    assert result.category is Category.STATUS_QUERY
    assert result.rule_id == "unmatched.status_query"
    assert result.reply == "I don't know, you tell me."
    assert result.matched is False


def test_declared_answer_sheet_entry_still_wins_over_ground_truth() -> None:
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet_with_ground_truth())  # type: ignore[arg-type]

    result = bank.reply_for("Which source contains the orders?")

    assert result.rule_id == "source.answer.orders"
    assert result.ground_truth is False
    assert result.matched is True


def test_ground_truth_fact_leaking_an_obstacle_term_is_rejected() -> None:
    raw = sheet_with_ground_truth().to_mapping()  # type: ignore[union-attr]
    raw["obstacle_terms"] = ["proxy"]
    raw["ground_truth"]["value_column"]["fact"] = "It is probably a proxy issue."

    with pytest.raises(MatcherError, match="obstacle"):
        MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), answer_sheet_from_mapping(raw))  # type: ignore[arg-type]


def test_ground_truth_malformed_entry_is_a_load_error_not_a_silent_skip() -> None:
    raw = sheet().to_mapping()  # type: ignore[union-attr]
    raw["ground_truth"] = {"value_column": {"terms": ["value"]}}  # missing "fact"

    with pytest.raises(ValueError, match="terms and fact"):
        answer_sheet_from_mapping(raw)


def test_ground_truth_unknown_key_is_a_load_error() -> None:
    raw = sheet().to_mapping()  # type: ignore[union-attr]
    raw["ground_truth"] = {"value_column": {"terms": ["value"], "fact": "It is dollars.", "surprise": True}}

    with pytest.raises(ValueError, match="unknown key"):
        answer_sheet_from_mapping(raw)


def test_ground_truth_key_absent_defaults_to_empty_and_round_trips() -> None:
    plain = sheet()
    assert plain.ground_truth == {}  # type: ignore[union-attr]
    assert plain.to_mapping()["ground_truth"] == {}  # type: ignore[union-attr]


def test_ground_truth_generic_single_word_term_does_not_match_inside_a_longer_word() -> None:
    """Word-boundary matching, not substring: 'column'/'value' must not fire on 'columns'/'values'.

    Regression for a confidently irrelevant answer: before word-boundary
    matching, both declared terms of ``value_column`` were satisfied by their
    plurals alone, so a general inventory question about a scenario with no
    real "value column" question would still get a scripted answer.
"""

    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet_with_ground_truth())  # type: ignore[arg-type]

    result = bank.reply_for("What columns and values are recognized in the export?")

    assert result.ground_truth is False
    assert result.rule_id != "ground_truth.value_column"


def test_ground_truth_exact_whole_word_terms_still_match() -> None:
    bank = MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet_with_ground_truth())  # type: ignore[arg-type]

    result = bank.reply_for("What does the value column represent?")

    assert result.rule_id == "ground_truth.value_column"
    assert result.ground_truth is True


def test_ground_truth_selection_uses_sorted_fact_ids_for_repeatable_selection() -> None:
    """When two facts' term sets both match, the lower fact_id (sorted first) wins.

    Mirrors ``test_answer_maps_use_sorted_keys_for_repeatable_selection`` for
    source/status/decision answers, which had no ground_truth arm.
    """

    raw = sheet().to_mapping()  # type: ignore[union-attr]
    raw["ground_truth"] = {
        "zeta_fact": {"terms": ["overlap"], "fact": "Zeta wins if selection were unsorted."},
        "alpha_fact": {"terms": ["overlap"], "fact": "Alpha is the correct sorted-first answer."},
    }
    populated = answer_sheet_from_mapping(raw)

    result = populated.answer_for_ground_truth("Please explain the overlap case.")  # type: ignore[union-attr]

    assert result == ("alpha_fact", "Alpha is the correct sorted-first answer.")


def test_ground_truth_fact_text_reaches_to_mapping_for_script_hashing() -> None:
    """The fact string must be part of the material operator_script_hash hashes.

    Without this, a regression dropping or constant-folding ``fact`` in
    ``GroundTruthFact.to_mapping`` would make two scenario variants differing
    only in ground-truth wording hash identically.
    """

    populated = sheet_with_ground_truth()

    mapping = populated.to_mapping()["ground_truth"]  # type: ignore[union-attr]

    assert mapping["value_column"]["fact"] == "The value column is the recognized dollar amount for that line."
    assert mapping["pii_policy"]["fact"] == "customer_email and salary are dropped entirely, never masked."
