"""Acceptance tests for the B8 product-usage fixture and reference oracle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.synthgen import generate_dataset
from dp_scenarios.synthgen.datasets import get_dataset
from dp_scenarios.synthgen.defects import _sentinel_for
from dp_scenarios.synthgen.reference import read_source_table, reference_gold


ROOT = Path(__file__).parents[1]
GOLD = ROOT / "scenarios/product-usage/gold"


def _json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fixture_is_deterministic_and_has_the_exact_declared_row_counts(tmp_path: Path) -> None:
    dataset = get_dataset("product_usage")
    assert dataset.plant == "B8-late-arrival-refresh"
    assert dataset.requires_explicit_plant is True
    assert dataset.source_tables == (
        "usage_events_v1",
        "usage_events_v2",
        "usage_events_v3",
        "usage_export_status_v1",
        "usage_export_status_v2",
        "usage_export_status_v3",
    )

    first = generate_dataset("product_usage", 29, tmp_path / "first")
    second = generate_dataset("product_usage", 29, tmp_path / "second")
    assert first.manifest["fixture_hash"] == second.manifest["fixture_hash"]

    v1 = read_source_table(first.data_dir.parent / "source", "usage_events_v1")
    v2 = read_source_table(first.data_dir.parent / "source", "usage_events_v2")
    v3 = read_source_table(first.data_dir.parent / "source", "usage_events_v3")
    assert len(v1) == 8_400
    assert len(v2) == 8_430
    assert len(v3) == 8_130
    assert len({row["event_id"] for row in v1}) == 8_400
    assert len({row["event_id"] for row in v2}) == 8_430
    assert len({row["event_id"] for row in v3}) == 8_130

    # The last v1 event lands at 23:57:36Z: 599 * 144 seconds into 2024-04-21.
    last_v1_day = [row for row in v1 if row["occurred_at"].startswith("2024-04-21")]
    assert max(row["occurred_at"] for row in last_v1_day) == "2024-04-21T23:57:36Z"

    status_v1 = read_source_table(first.data_dir.parent / "source", "usage_export_status_v1")
    status_v2 = read_source_table(first.data_dir.parent / "source", "usage_export_status_v2")
    status_v3 = read_source_table(first.data_dir.parent / "source", "usage_export_status_v3")
    assert status_v1 == [
        {"as_of": "2024-04-22T06:00:00Z", "expected_daily_count": 600, "reporting_date": "2024-04-21"}
    ]
    assert status_v2[0]["reporting_date"] == "2024-04-22"
    assert status_v3[0]["reporting_date"] == "2024-04-23"

    # This is a synthetic operator decoy: the sentinel is confined to account
    # 1's actor.email and generated from the fixture seed.
    marker = _sentinel_for("actor.email", seed=29, dataset="product_usage")
    account_1_emails = {row["actor"]["email"] for row in v1 if row["account_id"] == "ACC-0001"}
    assert account_1_emails == {marker}
    other_emails = {row["actor"]["email"] for row in v1 if row["account_id"] != "ACC-0001"}
    assert marker not in other_emails
    description = first.manifest["description"].casefold()
    for giveaway in ("late", "lookback", "duplicate", "actor"):
        assert giveaway not in description


def test_v3_short_day_delivers_exactly_half_the_expected_daily_events(tmp_path: Path) -> None:
    """B8b's planted short delivery: 300 of the 600 events expected for 2024-04-23."""

    generated = generate_dataset("product_usage", 29, tmp_path / "fixture")
    v3 = read_source_table(generated.data_dir.parent / "source", "usage_events_v3")
    apr23 = [row for row in v3 if row["occurred_at"].startswith("2024-04-23")]
    assert len(apr23) == 300
    status_v3 = read_source_table(generated.data_dir.parent / "source", "usage_export_status_v3")
    assert status_v3[0]["expected_daily_count"] == 600


def test_independent_gold_matches_the_frozen_committed_gold(tmp_path: Path) -> None:
    generated = generate_dataset("product_usage", 29, tmp_path / "fixture")

    answer = _json(generated.gold_dir / "product_usage_answer.json")
    adoption = _json(generated.gold_dir / "product_usage_feature_adoption.json")
    controls = _json(generated.gold_dir / "product_usage_controls.json")
    diagnostics = _json(generated.gold_dir / "product_usage_diagnostics.json")

    assert answer == _json(GOLD / "product_usage_answer.json")
    assert adoption == _json(GOLD / "product_usage_feature_adoption.json")
    assert controls == _json(GOLD / "product_usage_controls.json")
    assert diagnostics == _json(GOLD / "product_usage_diagnostics.json")

    assert answer == [
        {"week_start": "2024-04-08", "active_accounts": 200},
        {"week_start": "2024-04-15", "active_accounts": 130},
        {"week_start": "2024-04-22", "active_accounts": 100},
    ]
    assert {(row["week_start"], row["feature"]): row["active_accounts"] for row in adoption} == {
        ("2024-04-08", "search"): 200,
        ("2024-04-08", "dashboard"): 200,
        ("2024-04-08", "export"): 200,
        ("2024-04-15", "search"): 110,
        ("2024-04-15", "dashboard"): 110,
        ("2024-04-15", "export"): 110,
        ("2024-04-22", "search"): 100,
        ("2024-04-22", "dashboard"): 100,
        ("2024-04-22", "export"): 100,
    }
    assert diagnostics["expected_model_row_counts"] == {
        "usage_events": 9_030,
        "weekly_active_accounts": 3,
        "weekly_feature_adoption": 9,
        "usage_export_status": 1,
    }
    assert diagnostics["source_row_counts"] == {"v1": 8_400, "v2": 8_430, "v3": 8_130}
    assert len(diagnostics["late_event_ids"]) == 30
    assert diagnostics["earliest_late_timestamp"] == "2024-04-19T12:00:00Z"

    marker = _sentinel_for("actor.email", seed=29, dataset="product_usage")
    for path in generated.gold_dir.glob("*.json"):
        assert marker not in path.read_text(encoding="utf-8")


def test_a_naive_high_watermark_undercounts_the_correct_union(tmp_path: Path) -> None:
    """9,000 (a plausible naive high-watermark reread) is not the correct 9,030."""

    generated = generate_dataset("product_usage", 29, tmp_path / "fixture")
    source_dir = generated.data_dir.parent / "source"
    v1 = read_source_table(source_dir, "usage_events_v1")
    v2 = read_source_table(source_dir, "usage_events_v2")
    naive_watermark = max(row["occurred_at"] for row in v1)
    naive_count = len({row["event_id"] for row in v1}) + len(
        {row["event_id"] for row in v2 if row["occurred_at"] > naive_watermark}
    )
    assert naive_count == 9_000
    diagnostics = _json(generated.gold_dir / "product_usage_diagnostics.json")
    assert diagnostics["expected_model_row_counts"]["usage_events"] == 9_030
    assert naive_count != diagnostics["expected_model_row_counts"]["usage_events"]


def test_full_replace_from_v2_alone_drops_the_first_served_day(tmp_path: Path) -> None:
    """Replacing the landed set with v2 instead of unioning loses 2024-04-08's accounts."""

    generated = generate_dataset("product_usage", 29, tmp_path / "fixture")
    source_dir = generated.data_dir.parent / "source"
    v2 = read_source_table(source_dir, "usage_events_v2")
    assert len(v2) == 8_430
    diagnostics = _json(generated.gold_dir / "product_usage_diagnostics.json")
    assert 8_430 != diagnostics["expected_model_row_counts"]["usage_events"]


def test_reference_rejects_a_conflicting_duplicate_event_id(tmp_path: Path) -> None:
    generated = generate_dataset("product_usage", 29, tmp_path / "fixture")
    source_dir = generated.data_dir.parent / "source"
    v2_path = source_dir / "usage_events_v2.json"
    v2 = json.loads(v2_path.read_text(encoding="utf-8"))
    mutated = dict(v2[0])
    mutated["feature"] = "export" if mutated["feature"] != "export" else "search"
    v2.append(mutated)
    v2_path.write_text(json.dumps(v2), encoding="utf-8")

    with pytest.raises(ValueError, match=f"conflicting duplicate usage event {mutated['event_id']!r}"):
        reference_gold("product_usage", generated.data_dir, source_dir=source_dir)
