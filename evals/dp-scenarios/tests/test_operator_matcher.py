"""Deterministic matcher and no-leading reply tests."""

from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping
from dp_scenarios.operator.matcher import Category, MatcherBank, MatcherError
from dp_scenarios.operator.persona import load_persona, persona_from_mapping


ROOT = Path(__file__).parents[1]


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
