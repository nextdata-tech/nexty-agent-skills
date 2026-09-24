"""Every public checker fixture is deliberately hidden or deliberately visible."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "evals"
PUBLIC = EVALS / "public"


def _load_runner():
    if str(EVALS) not in sys.path:
        sys.path.insert(0, str(EVALS))
    spec = importlib.util.spec_from_file_location(
        "_eval_run_public_checker_isolation", EVALS / "run.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


run = _load_runner()


def _public_checker_paths() -> set[str]:
    return {
        path.relative_to(PUBLIC).as_posix()
        for scenario in PUBLIC.iterdir()
        if scenario.is_dir()
        for path in (scenario / "fixtures").glob("check*.py")
        if path.is_file()
    }


def test_every_public_checker_is_hidden_or_exactly_allowlisted() -> None:
    checkers = _public_checker_paths()
    allowlist = run.PUBLIC_CHECKER_VISIBLE_EXCEPTIONS
    allowed_paths = set(allowlist)

    stale = sorted(allowed_paths - checkers)
    assert not stale, f"visible checker allowlist has stale paths: {stale}"
    assert len(allowlist) == len(allowed_paths)
    assert set(run.PUBLIC_AGENT_RUN_SELF_CHECKS) <= allowed_paths

    unclassified: list[str] = []
    double_classified: list[str] = []
    for relative in sorted(checkers):
        scenario_name, _, fixture_name = relative.partition("/fixtures/")
        hidden = fixture_name in run.workspace_fixture_exclusions(scenario_name)
        visible = relative in allowed_paths
        if hidden and visible:
            double_classified.append(relative)
        elif not hidden and not visible:
            unclassified.append(relative)
        if visible:
            assert allowlist[relative].strip(), f"visible checker needs a rationale: {relative}"

    assert not double_classified, f"checkers are both hidden and visible: {double_classified}"
    assert not unclassified, (
        "public checker fixtures default to hidden; explicitly classify these: "
        f"{unclassified}"
    )


def test_agent_run_self_check_exceptions_are_required_by_their_scenarios() -> None:
    for relative in sorted(run.PUBLIC_AGENT_RUN_SELF_CHECKS):
        scenario_name, _, fixture_name = relative.partition("/fixtures/")
        scenario = PUBLIC / scenario_name
        prompt = (scenario / "prompt.md").read_text(encoding="utf-8")
        checks = json.loads((scenario / "checks.json").read_text(encoding="utf-8"))
        serialized_checks = json.dumps(checks)

        assert fixture_name in prompt, f"visible self-check is not named by {scenario_name}/prompt.md"
        assert fixture_name in serialized_checks, (
            f"visible self-check is not part of {scenario_name}/checks.json"
        )
        assert "deterministic_check" not in checks, (
            f"{relative} is a task-facing self-check, not a runner-side oracle"
        )


def test_runner_side_visible_legacy_checkers_execute_from_source_fixtures() -> None:
    for relative in (
        "treasury-yield-curve/fixtures/check_determinism.py",
        "coauthor-supplied-rubric/fixtures/check_coauthored_closure.py",
    ):
        scenario_name, _, fixture_name = relative.partition("/fixtures/")
        scenario = PUBLIC / scenario_name
        checks = json.loads((scenario / "checks.json").read_text(encoding="utf-8"))
        assert checks["deterministic_check"]["script"] == fixture_name
        assert fixture_name not in run.workspace_fixture_exclusions(scenario_name)
        assert relative in run.PUBLIC_CHECKER_VISIBLE_EXCEPTIONS


def test_google_sheets_and_openapi_source_codegen_checkers_are_hidden() -> None:
    assert "check_google_sheets_source.py" in run.workspace_fixture_exclusions(
        "google-sheets-source-codegen"
    )
    assert "check_openapi_api_source.py" in run.workspace_fixture_exclusions(
        "openapi-api-source-codegen"
    )
