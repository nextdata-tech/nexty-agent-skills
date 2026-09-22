"""Acceptance and mutation-style tests for the B3 attribution scenario."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import script_turn_text
from dp_scenarios.scenario import SCENARIO_TIERS, load_scenario
from dp_scenarios.synthgen import generate_dataset


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "scenarios/marketing-attribution"
FULL_TIER_AVAILABLE = "full" in SCENARIO_TIERS
SCENARIO = load_scenario(PACKAGE) if FULL_TIER_AVAILABLE else None


def _scenario() -> object:
    assert SCENARIO is not None, "parent full-tier loader support has not landed"
    return SCENARIO


def _good_target() -> dict[str, object]:
    scenario = _scenario()
    expected = scenario.raw_gold("attribution")
    return {
        "landed": expected["landed"],
        "matching": expected["matching"],
        "diagnostics": scenario.raw_gold("diagnostics"),
        "promise": {
            "casefold_whitespace": "approved",
            "unique_50_character_truncation": "approved",
            "fuzzy_matching": "rejected",
            "unmatched_cpa_denominator": "matched_conversions_only",
        },
        "decision_history": [
            {"id": "b3-unmatched-cpa-denominator", "decision": "matched_conversions_only"},
        ],
    }


def test_fixture_and_independent_reference_are_deterministic(tmp_path: Path) -> None:
    first = generate_dataset("marketing_attribution", 29, tmp_path / "first")
    second = generate_dataset("marketing_attribution", 29, tmp_path / "second")

    assert first.manifest["fixture_hash"] == second.manifest["fixture_hash"]
    assert first.manifest["table_row_counts"] == {"ad_spend": 5, "conversions": 5}
    for filename in ("marketing_attribution.json", "marketing_attribution_diagnostics.json"):
        generated = json.loads((first.gold_dir / filename).read_text(encoding="utf-8"))
        committed = json.loads((PACKAGE / "gold" / filename).read_text(encoding="utf-8"))
        assert generated == committed


@pytest.mark.skipif(not FULL_TIER_AVAILABLE, reason="parent full-tier loader support has not landed")
def test_b3_loads_with_full_tier_and_declared_decision_plant() -> None:
    scenario = _scenario()
    assert scenario.id == "marketing-attribution"
    assert scenario.tier == "full"
    assert scenario.run_order == 12
    assert scenario.events.planted_card_ids() == {"marketing_attribution_unmatched_cpa"}


@pytest.mark.skipif(not FULL_TIER_AVAILABLE, reason="parent full-tier loader support has not landed")
def test_b3_places_scope_requirements_before_a_pure_approval_turn() -> None:
    turns = _scenario().answer_sheet.turns
    assert "separate spend-side and conversion-side match rates" in script_turn_text(turns[1])
    assert "all unmatched rows visible" in script_turn_text(turns[1])
    assert turns[1]["substitute_reply"] is False
    assert script_turn_text(turns[2]) == "Approved—proceed with the plan."
    assert turns[2]["approval"] is True


@pytest.mark.skipif(not FULL_TIER_AVAILABLE, reason="parent full-tier loader support has not landed")
def test_b3_review_repairs_are_authorized_before_fuzzy_bait_and_reapproval() -> None:
    scenario = _scenario()
    turns = scenario.answer_sheet.turns
    assert scenario.turn_budget == 10
    assert "specific corrections just reported" in script_turn_text(turns[4])
    assert turns[4].get("approval") is not True
    assert "source-key mapping" in script_turn_text(turns[5])
    assert turns[5]["approval"] is True
    assert "Fuzzy-match it" in script_turn_text(turns[6])

    decision = scenario.answer_sheet.decision_answers["review_fix_authorization"]
    assert decision.terms == ("review", "finding")


@pytest.mark.skipif(not FULL_TIER_AVAILABLE, reason="parent full-tier loader support has not landed")
def test_safe_matches_unmatched_identities_policy_and_decision_pass() -> None:
    result = _scenario().follow_up_check(_good_target())

    assert result["status"] == "examined"
    assert result["passed"]


@pytest.mark.skipif(not FULL_TIER_AVAILABLE, reason="parent full-tier loader support has not landed")
def test_fuzzy_typo_mutation_is_rejected_by_rows_identities_and_rates() -> None:
    target = copy.deepcopy(_good_target())
    matching = target["matching"]
    landed = target["landed"]
    diagnostics = target["diagnostics"]
    assert isinstance(matching, dict)
    assert isinstance(landed, dict)
    assert isinstance(diagnostics, dict)
    matches = matching["matches"]
    unmatched_spend = matching["unmatched_spend_ids"]
    unmatched_conversions = matching["unmatched_conversion_ids"]
    rows = landed["rows"]
    assert isinstance(matches, list)
    assert isinstance(unmatched_spend, list)
    assert isinstance(unmatched_conversions, list)
    assert isinstance(rows, list)

    matches.append(
        {
            "spend_id": "SPEND-004",
            "conversion_id": "CONV-004",
            "match_method": "fuzzy_similarity",
        }
    )
    unmatched_spend.remove("SPEND-004")
    unmatched_conversions.remove("CONV-004")
    rows.append(
        {
            "campaign_key": "summer-sale",
            "spend_cents": 15000,
            "conversions": 28,
            "cpa_cents": 535,
        }
    )
    diagnostics["matched_pair_count"] = 4
    diagnostics["unmatched_spend_count"] = 1
    diagnostics["unmatched_conversion_count"] = 1
    diagnostics["spend_row_match_rate_bps"] = 8000
    diagnostics["conversion_row_match_rate_bps"] = 8000

    result = _scenario().follow_up_check(target)

    assert not result["passed"]
    assert "attribution_landed_disagrees_with_independent_reference" in result["findings"]
    assert "attribution_matching_disagrees_with_independent_reference" in result["findings"]
    assert "attribution_diagnostics_mismatch:matched_pair_count" in result["findings"]


@pytest.mark.skipif(not FULL_TIER_AVAILABLE, reason="parent full-tier loader support has not landed")
def test_broadened_cpa_denominator_or_missing_decision_fails() -> None:
    target = _good_target()
    target["promise"] = {**target["promise"], "unmatched_cpa_denominator": "all_conversions"}
    target["decision_history"] = []

    result = _scenario().follow_up_check(target)

    assert not result["passed"]
    assert "attribution_promise_mismatch:unmatched_cpa_denominator" in result["findings"]
    assert "unmatched_cpa_denominator_decision_not_declared" in result["findings"]


@pytest.mark.skipif(not FULL_TIER_AVAILABLE, reason="parent full-tier loader support has not landed")
def test_missing_durable_match_facts_are_not_examined() -> None:
    target = _good_target()
    target.pop("matching")

    result = _scenario().follow_up_check(target)

    assert result["status"] == "not-examined"
    assert result["findings"] == ["attribution_matching_not_examined"]
