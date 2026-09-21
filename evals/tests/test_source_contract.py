"""Tests for the self-contained source/coverage/ratio recipe."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "src" / "nxd-generate-data-product" / "scripts" / "source_contract.py"


def _recipe():
    spec = importlib.util.spec_from_file_location("source_contract_recipe", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_read_csv_rows_checks_required_and_duplicate_headers(tmp_path: Path):
    recipe = _recipe()
    source = _write(tmp_path / "source.csv", "id,name\n1,one\n")
    assert recipe.read_csv_rows(
        source, required_columns=("id",), source_name="source"
    ) == [{"id": "1", "name": "one"}]

    with pytest.raises(RuntimeError, match="missing required columns"):
        recipe.read_csv_rows(
            source, required_columns=("campaign_name",), source_name="source"
        )

    missing_value = _write(tmp_path / "missing-value.csv", "id,name\n1\n")
    with pytest.raises(RuntimeError, match="missing values"):
        recipe.read_csv_rows(
            missing_value, required_columns=("id", "name"), source_name="source"
        )

    duplicate = _write(tmp_path / "duplicate.csv", "id,id\n1,one\n")
    with pytest.raises(RuntimeError, match="duplicate headers"):
        recipe.read_csv_rows(
            duplicate, required_columns=("id",), source_name="source"
        )

    with pytest.raises(ValueError, match="required_columns must not be empty"):
        recipe.read_csv_rows(source, required_columns=(), source_name="source")


def test_read_csv_rows_can_require_an_exact_header_set(tmp_path: Path):
    recipe = _recipe()
    source = _write(tmp_path / "source.csv", "id,name\n1,one\n")
    with pytest.raises(RuntimeError, match="approved header set"):
        recipe.read_csv_rows(
            source,
            required_columns=("id",),
            expected_columns=("id",),
            source_name="source",
        )


def test_coverage_summary_reports_each_side_and_rejects_unknown_ids():
    recipe = _recipe()
    summary = recipe.coverage_summary(
        [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        ["A", "B"],
        id_column="id",
        source_name="spend",
    )
    assert summary == {
        "source": "spend",
        "row_count": 3,
        "matched_count": 2,
        "coverage_bps": 6667,
        "unmatched_ids": ["C"],
    }
    with pytest.raises(RuntimeError, match="not in the source"):
        recipe.coverage_summary(
            [{"id": "A"}], ["MISSING"], id_column="id", source_name="spend"
        )


def test_aggregate_ratio_uses_additive_totals_not_sum_of_row_ratios():
    recipe = _recipe()
    source = [
        {"spend_cents": "100", "conversions": "1"},
        {"spend_cents": "100", "conversions": "3"},
    ]
    recipe.assert_aggregate_ratio(
        source,
        {"cpa_cents": "50"},
        numerator_column="spend_cents",
        denominator_column="conversions",
        ratio_column="cpa_cents",
        metric_name="cpa",
    )
    with pytest.raises(RuntimeError, match="do not sum row-level ratios"):
        recipe.assert_aggregate_ratio(
            source,
            {"cpa_cents": "133"},
            numerator_column="spend_cents",
            denominator_column="conversions",
            ratio_column="cpa_cents",
            metric_name="cpa",
        )


def test_row_ratio_assertion_covers_the_non_aggregate_path():
    recipe = _recipe()
    rows = [
        {"spend_cents": "100", "conversions": "2", "cpa_cents": "50"},
        {"spend_cents": "100", "conversions": "4", "cpa_cents": "25"},
    ]
    recipe.assert_row_ratios(
        rows,
        numerator_column="spend_cents",
        denominator_column="conversions",
        ratio_column="cpa_cents",
        metric_name="cpa",
    )
    rows[1]["cpa_cents"] = "24"
    with pytest.raises(RuntimeError, match="does not equal"):
        recipe.assert_row_ratios(
            rows,
            numerator_column="spend_cents",
            denominator_column="conversions",
            ratio_column="cpa_cents",
            metric_name="cpa",
        )


def test_ratio_rejects_non_positive_denominator():
    recipe = _recipe()
    with pytest.raises(RuntimeError, match="positive denominator"):
        recipe.ratio_cents(1, 0, metric_name="cpa")


def test_recipe_source_runs_after_copying_into_a_closure(tmp_path: Path):
    """The shipped recipe is executable after leaving the skill tree."""
    copied = tmp_path / "transform" / "main.py"
    copied.parent.mkdir()
    copied.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("copied_source_contract", copied)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.ratio_cents("100", "4", metric_name="cpa") == 25
