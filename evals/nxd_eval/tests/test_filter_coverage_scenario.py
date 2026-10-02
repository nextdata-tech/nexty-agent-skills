"""Regression coverage for the local-mesh filter scenario authoring."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_filter_coverage_import_does_not_require_mesh_environment(monkeypatch):
    monkeypatch.delenv("NXD_EVAL_DP_URL", raising=False)
    monkeypatch.delenv("EVAL_MESH_TOKEN", raising=False)

    scenario = importlib.import_module("scenarios.filter_coverage")
    importlib.reload(scenario)

    assert scenario.filter_coverage_suite().name == "local-mesh-filter-coverage"


def test_filter_coverage_gold_pins_slot_selection_and_filter_metadata():
    from scenarios.filter_coverage import filter_coverage_suite

    suite = filter_coverage_suite()
    expected_groups = {
        "q1": ["product_name"],
        "q2": ["specialty_group"],
        "q3": ["region_name"],
        "q4": [],
    }
    expected_filters = {
        "q1": [
            {"field": "region_name", "op": "=", "value": "NE Gulf Coast"},
            {
                "field": "specialty_group",
                "op": "=",
                "value": "Psychiatry & Neurology",
            },
        ],
        "q2": [
            {
                "field": "specialty_group",
                "op": "IN",
                "value": ["Neurology", "Psychiatry & Neurology"],
            }
        ],
        "q3": [],
        "q4": [
            {"field": "product_name", "op": "=", "value": "BETAMAB"},
            {"field": "region_name", "op": "=", "value": "SW Desert"},
        ],
    }

    for case in suite.cases:
        record = suite.gold[case.gold_id]
        assert record["measures"] == ["enrolled_patients"]
        assert record["group_by"] == expected_groups[case.id]
        assert case.metadata["gold_selection"]["measures"] == ["enrolled_patients"]
        assert case.metadata["gold_selection"]["group_by"] == expected_groups[case.id]
        assert case.metadata["gold_selection"]["filters"] == expected_filters[case.id]
        assert record["rows"]

    assert suite.gold["q4"]["rows"] == [{"enrolled_patients": 0}]


def test_filter_coverage_server_factory_reads_url_and_mesh_token_lazily(
    monkeypatch,
):
    from scenarios import filter_coverage

    captured = {}
    monkeypatch.setenv("NXD_EVAL_DP_URL", "https://mesh.example/dp/rpcs/mcp-api/mcp")
    monkeypatch.setenv("EVAL_MESH_TOKEN", "test-token")
    monkeypatch.setattr(
        filter_coverage,
        "mcp_server_http",
        lambda **kwargs: captured.update(kwargs) or object(),
    )

    filter_coverage.server_factory()

    assert captured["url"] == "https://mesh.example/dp/rpcs/mcp-api/mcp"
    assert captured["headers"] == {"X-Nextdata-Token": "test-token"}
