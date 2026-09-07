"""Acceptance tests for the deterministic C6 locale/timezone package."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from dp_scenarios.scenario import load_scenario
from dp_scenarios.synthgen.reference import reference_gold


ROOT = Path(__file__).parents[1]
SCENARIO = load_scenario(ROOT / "scenarios/locale-timezone")


def _evidence() -> dict[str, object]:
    return {
        "time_policy": {
            "source_timezone": "America/New_York",
            "daily_boundary": "source_local",
            "utc_conversion": "retain_utc_for_audit",
        },
        "daily_comparison": {
            "source_local_total": "2310.00",
            "utc_total": "2310.00",
            "totals_invariant": True,
            "boundary_shift_rows": 1,
            "boundary_shift_fraction": 0.07142857,
            "source_local_daily": [
                {"day": "2024-03-01", "row_count": 1, "total_amount": "100.00"},
                {"day": "2024-03-02", "row_count": 1, "total_amount": "110.00"},
                {"day": "2024-03-03", "row_count": 1, "total_amount": "120.00"},
                {"day": "2024-03-04", "row_count": 1, "total_amount": "130.00"},
                {"day": "2024-03-05", "row_count": 1, "total_amount": "140.00"},
                {"day": "2024-03-06", "row_count": 1, "total_amount": "150.00"},
                {"day": "2024-03-07", "row_count": 1, "total_amount": "160.00"},
                {"day": "2024-03-08", "row_count": 1, "total_amount": "170.00"},
                {"day": "2024-03-09", "row_count": 1, "total_amount": "180.00"},
                {"day": "2024-03-10", "row_count": 3, "total_amount": "620.00"},
                {"day": "2024-03-11", "row_count": 1, "total_amount": "210.00"},
                {"day": "2024-03-12", "row_count": 1, "total_amount": "220.00"},
            ],
            "utc_daily": [
                {"day": "2024-03-01", "row_count": 1, "total_amount": "100.00"},
                {"day": "2024-03-02", "row_count": 1, "total_amount": "110.00"},
                {"day": "2024-03-03", "row_count": 1, "total_amount": "120.00"},
                {"day": "2024-03-04", "row_count": 1, "total_amount": "130.00"},
                {"day": "2024-03-05", "row_count": 1, "total_amount": "140.00"},
                {"day": "2024-03-06", "row_count": 1, "total_amount": "150.00"},
                {"day": "2024-03-07", "row_count": 1, "total_amount": "160.00"},
                {"day": "2024-03-08", "row_count": 1, "total_amount": "170.00"},
                {"day": "2024-03-09", "row_count": 1, "total_amount": "180.00"},
                {"day": "2024-03-10", "row_count": 2, "total_amount": "390.00"},
                {"day": "2024-03-11", "row_count": 2, "total_amount": "440.00"},
                {"day": "2024-03-12", "row_count": 1, "total_amount": "220.00"},
            ],
        },
        "unicode_query": {"category": "契約", "row_count": 7},
        "decision": {
            "id": "c6-source-local-day",
            "status": "confirmed",
            "reporting_definition": {"day_boundary": "source_local", "utc_role": "audit"},
        },
    }


def test_c6_loads_as_core_and_declares_the_timezone_plant() -> None:
    assert SCENARIO.tier == "core"
    assert SCENARIO.run_order == 11
    assert SCENARIO.plant_vocabulary == {"locale_timezone_boundary"}
    assert SCENARIO.events.planted_card_ids() == SCENARIO.required_plants


def test_c6_driver_guard_covers_each_ground_truth_trigger_term() -> None:
    ground_truth_terms = {
        term
        for fact in SCENARIO.answer_sheet.ground_truth.values()
        for term in fact.terms
    }
    assert ground_truth_terms <= set(SCENARIO.answer_sheet.driver_forbidden_terms)


def test_c6_preserves_non_ascii_source_values_and_has_one_boundary_shift(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "c6")
    with (generated.data_dir / "events.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 14
    assert {row["category"] for row in rows} == {"Renovación", "契約"}
    assert sum(row["source_local_timestamp"][:10] != row["event_utc"][:10] for row in rows) == 1
    assert rows[9]["source_local_timestamp"].endswith("-05:00")
    assert rows[10]["source_local_timestamp"].endswith("-04:00")
    assert rows[13]["event_utc"].startswith("2024-03-11")


def test_c6_query_gold_scores_the_unicode_category_count(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "c6")
    assert SCENARIO.has_scoreable_answer_gold
    gold = SCENARIO.load_gold("answer", generated.out_dir)
    correct = SCENARIO.score_query(gold.rows, generated.out_dir)
    wrong = SCENARIO.score_query(
        [{"category": "契約", "row_count": 6}],
        generated.out_dir,
    )
    assert correct.verdict == "correct"
    assert correct.gold_gate.passed
    assert wrong.verdict == "other_wrong"
    assert not wrong.gold_gate.passed


def test_c6_requires_timezone_policy_daily_comparison_and_unicode_query() -> None:
    result = SCENARIO.follow_up_check(_evidence())
    assert result["passed"]
    assert SCENARIO.follow_up_gate(
        _evidence(),
        fired_plants={"fired_plant_ids": ["locale_timezone_boundary"]},
    ).passed

    changed = _evidence()
    changed["daily_comparison"] = {
        **changed["daily_comparison"],
        "boundary_shift_rows": 0,
    }
    failed = SCENARIO.follow_up_check(changed)
    assert not failed["passed"]
    assert "boundary_shift_mismatch:boundary_shift_rows" in failed["findings"]


@pytest.mark.parametrize("missing", ("time_policy", "daily_comparison", "unicode_query", "decision"))
def test_c6_missing_required_evidence_is_not_examined(missing: str) -> None:
    evidence = _evidence()
    del evidence[missing]
    result = SCENARIO.follow_up_check(evidence)
    assert result["status"] == "not-examined"
    assert not result["passed"]


def test_c6_grades_daily_amounts_independently_of_row_counts() -> None:
    evidence = _evidence()
    local_daily = list(evidence["daily_comparison"]["source_local_daily"])
    local_daily[9] = {**local_daily[9], "total_amount": "600.00"}
    evidence["daily_comparison"] = {
        **evidence["daily_comparison"],
        "source_local_daily": local_daily,
    }
    result = SCENARIO.follow_up_check(evidence)
    assert not result["passed"]
    assert "source_local_daily_rows_mismatch" in result["findings"]


def test_c6_reference_rejects_a_recorded_utc_value_that_is_not_derived_from_local_time(
    tmp_path: Path,
) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "c6")
    source = generated.data_dir / "events.csv"
    with source.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["event_utc"] = "2024-03-01T18:00:00+00:00"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="event_utc does not match"):
        reference_gold("locale_timezone", generated.data_dir)


def test_c6_reference_rejects_an_absent_declared_unicode_query_category(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "c6")
    source = generated.data_dir / "events.csv"
    with source.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["category"] = "Renovación"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="query category is absent"):
        reference_gold("locale_timezone", generated.data_dir)
