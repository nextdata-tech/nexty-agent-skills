"""Wiring checks for the opt-in optional-output Desktop E2E scenario."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCENARIO = ROOT / "evals/public/optional-empty-output-aggregate-desktop"


def test_optional_output_desktop_scenario_is_registered_fail_closed() -> None:
    checks = json.loads((SCENARIO / "checks.json").read_text(encoding="utf-8"))
    marker = json.loads((SCENARIO / "fixtures/desktop.json").read_text(encoding="utf-8"))
    assert checks["desktop_verify"] is True
    assert checks["ci_skip"]
    assert {"nxd-run-job-loop", "nxd-generate-data-product"} <= set(checks["skills"])
    assert marker["workflow"] == "mapper-aggregate-e2e"
    assert marker["verifier"] == "check_optional_empty_aggregate.py"
    assert (SCENARIO / "fixtures/reference-closure/spec.py").is_file()
    assert (SCENARIO / "fixtures/reference-closure/data/orders/orders.csv").is_file()


def test_optional_output_checker_is_withheld_from_the_agent_workspace() -> None:
    run_source = (ROOT / "evals/run.py").read_text(encoding="utf-8")
    assert '"optional-empty-output-aggregate-desktop": frozenset({' in run_source
    assert '"check_optional_empty_aggregate.py",' in run_source


def test_reference_closure_carries_optional_model_and_count_view() -> None:
    spec = (SCENARIO / "fixtures/reference-closure/spec.py").read_text(encoding="utf-8")
    models = (SCENARIO / "fixtures/reference-closure/models.py").read_text(encoding="utf-8")
    transform = (SCENARIO / "fixtures/reference-closure/transform/main.py").read_text(encoding="utf-8")
    assert ".promise(orders)" in spec
    assert ".model(reviews)" in spec
    assert ".model(order_metrics)" in spec
    assert 'semantic_view("order_metrics", orders)' in models
    assert 'metric(Agg.COUNT, of=orders.field("*")' in models
    assert 'OPTIONAL_EMPTY_MODELS = ("reviews",)' in transform
    assert "map_inputs(" in transform
