"""Acceptance tests for the deterministic C2 lineage-dispute package."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from dp_scenarios.scenario import load_scenario


ROOT = Path(__file__).parents[1]
SCENARIO = load_scenario(ROOT / "scenarios/application-reconciliation")


def _evidence() -> dict[str, object]:
    return {
        "reconciliation": {
            "export_count": 391,
            "dashboard_active_count": 353,
            "difference": 38,
            "status_filter_exclusions": 30,
            "tombstone_exclusions": 8,
        },
        "lineage": {
            "source_table": "applications",
            "dashboard_table": "dashboard_snapshot",
            "clauses": [
                {
                    "id": "active_status",
                    "predicate": "status != active",
                    "excludes": 30,
                },
                {
                    "id": "tombstone_filter",
                    "predicate": "status = active AND tombstoned = true",
                    "excludes": 8,
                },
            ],
            "disjoint_exclusion_total": 38,
        },
        "governed_query": {
            "grain": "reconciliation_metric",
            "filters": ["status = active", "tombstoned = false"],
            "metrics": {
                "export_applications": 391,
                "dashboard_active_applications": 353,
                "difference": 38,
                "status_filter_exclusions": 30,
                "tombstone_exclusions": 8,
            },
        },
        "decision": {
            "id": "c2-active-count-reconciliation",
            "status": "proposed",
            "population_definition": {"status": "active", "tombstoned": "false"},
        },
    }


def test_c2_loads_as_core_and_declares_the_reconciliation_plant() -> None:
    assert SCENARIO.tier == "core"
    assert SCENARIO.run_order == 10
    assert SCENARIO.plant_vocabulary == {"application_reconciliation_dispute"}
    assert SCENARIO.events.planted_card_ids() == SCENARIO.required_plants


def test_c2_driver_guard_uses_reconciliation_vocabulary() -> None:
    assert {
        "dashboard",
        "active",
        "tombstoned",
        "export",
        "rows",
        "withdrawn",
    }.issubset(SCENARIO.answer_sheet.driver_forbidden_terms)


def test_c2_source_has_391_rows_and_the_independent_filter_has_353(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "c2")
    with (generated.data_dir / "applications.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 391
    assert sum(row["status"] == "active" and row["tombstoned"] == "false" for row in rows) == 353
    assert sum(row["status"] != "active" for row in rows) == 30
    assert sum(row["status"] == "active" and row["tombstoned"] == "true" for row in rows) == 8
    assert sum(row["status"] != "active" and row["tombstoned"] == "true" for row in rows) == 8


def test_c2_query_gold_scores_the_reconciliation_metric(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "c2")
    assert SCENARIO.has_scoreable_answer_gold
    gold = SCENARIO.load_gold("answer", generated.out_dir)
    assert gold.rows == [
        {
            "reconciliation_snapshot_date": "2024-04-30",
            "export_applications": 391,
            "dashboard_active_applications": 353,
            "difference": 38,
            "status_filter_exclusions": 30,
            "tombstone_exclusions": 8,
        }
    ]
    correct = SCENARIO.score_query(gold.rows, generated.out_dir)
    wrong = SCENARIO.score_query(
        [{**gold.rows[0], "difference": 0, "dashboard_active_applications": 391}],
        generated.out_dir,
    )
    assert correct.verdict == "correct"
    assert correct.gold_gate.passed
    assert wrong.verdict == "other_wrong"
    assert not wrong.gold_gate.passed


def test_c2_requires_lineage_and_governed_query_evidence() -> None:
    result = SCENARIO.follow_up_check(_evidence())
    assert result["passed"]
    assert SCENARIO.follow_up_gate(
        _evidence(),
        fired_plants={"fired_plant_ids": ["application_reconciliation_dispute"]},
    ).passed


@pytest.mark.parametrize("missing", ("reconciliation", "lineage", "governed_query", "decision"))
def test_c2_missing_required_evidence_is_not_examined(missing: str) -> None:
    evidence = _evidence()
    del evidence[missing]
    result = SCENARIO.follow_up_check(evidence)
    assert result["status"] == "not-examined"
    assert not result["passed"]


def test_c2_rejects_a_transform_that_reports_only_the_dashboard_number() -> None:
    evidence = _evidence()
    evidence["reconciliation"] = {
        "export_count": 353,
        "dashboard_active_count": 353,
        "difference": 0,
        "status_filter_exclusions": 0,
        "tombstone_exclusions": 0,
    }
    result = SCENARIO.follow_up_check(evidence)
    assert not result["passed"]
    assert "reconciliation_mismatch:export_count" in result["findings"]


def test_c2_requires_both_query_filters_and_structured_clause_predicates() -> None:
    evidence = _evidence()
    evidence["governed_query"] = {
        **evidence["governed_query"],
        "filters": ["status = active"],
    }
    evidence["lineage"] = {
        **evidence["lineage"],
        "clauses": [
            {
                "id": "active_status",
                "predicate": "status = active",
                "excludes": 30,
            },
            evidence["lineage"]["clauses"][1],
        ],
    }
    result = SCENARIO.follow_up_check(evidence)
    assert not result["passed"]
    assert "governed_query_filters_incomplete" in result["findings"]
    assert "lineage_clause_mismatch:active_status:predicate" in result["findings"]
