"""Wiring checks for the opt-in optional-output Desktop E2E scenario."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SCENARIO = ROOT / "evals/public/optional-empty-output-aggregate-desktop"
CHECKER_PATH = SCENARIO / "fixtures/check_optional_empty_aggregate.py"
CHECKER_SPEC = importlib.util.spec_from_file_location("optional_empty_checker", CHECKER_PATH)
assert CHECKER_SPEC is not None and CHECKER_SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(CHECKER_SPEC)
CHECKER_SPEC.loader.exec_module(CHECKER)


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


def test_checker_ast_helpers_accept_qualified_calls_and_empty_annotations() -> None:
    models = """
import nxd.spec

empty: object
aggregate = nxd.spec.semantic_view("metrics", orders).fields({})
"""
    spec = """
from models import aggregate

output = nxd.spec.data_product_output().model(models.aggregate)
"""
    assert CHECKER._semantic_view_names(models) == {"aggregate"}
    assert CHECKER._output_model_names(spec) == {"aggregate"}
    assert CHECKER._semantic_view_names("empty: object = None") == set()


def test_checker_stop_reaps_recorded_supervisor_and_semantic_groups(tmp_path: Path) -> None:
    data_dir = tmp_path / "state"
    data_dir.mkdir()
    supervisor = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True
    )
    semantic = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True
    )
    (data_dir / "supervisor.pid").write_text(str(supervisor.pid), encoding="utf-8")
    (data_dir / "semantic.pid").write_text(str(semantic.pid), encoding="utf-8")
    try:
        fact = CHECKER._stop("/usr/bin/false", data_dir, supervisor)
        assert supervisor.poll() is not None
        assert semantic.poll() is not None
        assert fact.startswith("teardown_complete")
    finally:
        if supervisor.poll() is None:
            CHECKER._reap(supervisor)
        if semantic.poll() is None:
            CHECKER._reap_process_group(semantic.pid)
