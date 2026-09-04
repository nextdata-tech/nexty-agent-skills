"""The API scenario must mechanically detect response-envelope leakage."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


CHECKER = (
    Path(__file__).parents[1]
    / "public"
    / "authenticated-api-source-build"
    / "fixtures"
    / "check_authenticated_api_source.py"
)
CHECKS = CHECKER.parents[1] / "checks.json"
spec = importlib.util.spec_from_file_location("api_source_checker_envelope", CHECKER)
checker = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(checker)


def test_envelope_metadata_columns_are_reported():
    assert checker.envelope_metadata_columns(
        ["id", "page", "PER_PAGE", "total", "pages", "status"]
    ) == ["page", "pages", "PER_PAGE", "total"]


def test_normal_row_columns_are_not_reported_as_envelope_leakage():
    assert checker.envelope_metadata_columns(["id", "monitor_id", "status"]) == []


def test_envelope_fact_is_pinned_between_checks_and_fixture():
    checks = json.loads(CHECKS.read_text(encoding="utf-8"))
    check = next(item for item in checks["checks"] if item["id"] == "data-selector-or-envelope-handled")
    assert checker.ENVELOPE_FACT == "landed:envelope-metadata-absent"
    assert checker.ENVELOPE_FACT in check["check"]
    assert "does not by itself prove" in check["check"]
