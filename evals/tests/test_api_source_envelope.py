"""The API scenario must mechanically detect response-envelope leakage."""
from __future__ import annotations

import importlib.util
from pathlib import Path


CHECKER = (
    Path(__file__).parents[1]
    / "public"
    / "authenticated-api-source-build"
    / "fixtures"
    / "check_authenticated_api_source.py"
)
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
