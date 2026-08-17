"""Table resolution in the authenticated-api-source checker must not confuse a
derived model for a source table.

A closure that lands derived models named after BOTH domain nouns (the brief's
own vocabulary invites `check_monitor_resolution` and `monitor_coverage`) used to
collapse the monitors and checks lookups onto the SAME table, because the naive
substring scan returned whichever candidate sorted first. Every downstream
measurement — pagination counts, flattening, tri-state, orphans — was then taken
against the wrong axis and reported as an agent failure.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


CHECKER = (Path(__file__).parents[1] / "public" / "authenticated-api-source-build" /
           "fixtures" / "check_authenticated_api_source.py")
spec = importlib.util.spec_from_file_location("api_source_checker", CHECKER)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


# The exact SHOW TABLES output from the run that exposed the bug.
LANDED_TABLES = [
    "_dlt_loads",
    "_dlt_pipeline_state",
    "_dlt_version",
    "check_monitor_resolution",
    "checks",
    "monitor_coverage",
    "monitors",
]


@pytest.fixture(autouse=True)
def _reset_diagnostics():
    checker.FAILURES.clear()
    checker.PASSES.clear()
    yield
    checker.FAILURES.clear()
    checker.PASSES.clear()


def test_fallback_resolves_source_tables_not_derived_models():
    assert checker.find_table(LANDED_TABLES, "monitor", "check") == "monitors"
    assert checker.find_table(LANDED_TABLES, "check", "monitor") == "checks"
    assert checker.FAILURES == []


def test_fallback_reports_ambiguity_instead_of_guessing():
    tables = ["monitor_coverage", "monitor_rollup"]
    assert checker.find_table(tables, "monitor", "check") is None
    assert any("landed:table-resolution-ambiguous" in f for f in checker.FAILURES)


def test_declared_endpoints_win_over_substring(tmp_path: Path):
    (tmp_path / "api-source-endpoints").write_text(
        "monitors=/v1/monitors\nchecks=/v1/checks\n", encoding="utf-8")
    got, detail = checker.resolve_table(
        tmp_path, LANDED_TABLES, "/v1/monitors", "monitor", "check")
    assert (got, detail) == ("monitors", "")
    got, detail = checker.resolve_table(
        tmp_path, LANDED_TABLES, "/v1/checks", "check", "monitor")
    assert (got, detail) == ("checks", "")


def test_declared_model_with_no_landed_table_fails_loudly(tmp_path: Path):
    (tmp_path / "api-source-endpoints").write_text(
        "monitor_feed=/v1/monitors\n", encoding="utf-8")
    got, detail = checker.resolve_table(
        tmp_path, LANDED_TABLES, "/v1/monitors", "monitor", "check")
    assert got is None
    assert "monitor_feed" in detail
    assert "monitors" in detail


def test_companion_absent_falls_back(tmp_path: Path):
    got, _ = checker.resolve_table(
        tmp_path, LANDED_TABLES, "/v1/checks", "check", "monitor")
    assert got == "checks"
