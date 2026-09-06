"""Acceptance tests for the deterministic B2 finance-close package."""

from __future__ import annotations

from pathlib import Path

from dp_scenarios.scenario import load_scenario
from dp_scenarios.runner.environment import PinnedVersions, RunEnvironment
from dp_scenarios.synthgen import generate_dataset


ROOT = Path(__file__).parents[1]
SCENARIO = load_scenario(ROOT / "scenarios/finance-close")


def _pins() -> PinnedVersions:
    return PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1")


def _good_target() -> dict[str, object]:
    return {
        "landed": SCENARIO.raw_gold("reconciliation"),
        "promise": {
            "amount_parser": "comma_and_parentheses",
            "missing_fx_policy": "exclude_and_warn",
            "output_total": "eur",
            "rounding": "cents",
        },
        "diagnostics": SCENARIO.raw_gold("diagnostics"),
        "decision_history": [
            {"id": "b2-weekend-fx", "decision": "exclude_and_warn"},
            {"id": "b2-weekend-fx-reversal", "supersedes": "b2-weekend-fx", "decision": "preserve_unconverted"},
        ],
    }


def test_b2_loads_as_core_and_declares_the_reversal_plant() -> None:
    assert SCENARIO.run_order == 8
    assert SCENARIO.tier == "core"
    assert SCENARIO.dataset == "finance_close"
    assert SCENARIO.events.planted_card_ids() == {"finance_close_reconciliation"}


def test_hostile_decimal_reconciliation_and_supersession_pass() -> None:
    result = SCENARIO.follow_up_check(_good_target())
    assert result["status"] == "examined"
    assert result["passed"]


def test_wrong_total_or_missing_fx_policy_fails() -> None:
    target = _good_target()
    target["landed"] = {**target["landed"], "total_eur": "2861.50"}  # type: ignore[index]
    target["promise"] = {**target["promise"], "missing_fx_policy": "coerce_to_zero"}  # type: ignore[index]
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "landed_total_disagrees_with_independent_reference" in result["findings"]
    assert "output_promise_mismatch:missing_fx_policy" in result["findings"]


def test_absent_decision_history_is_not_examined() -> None:
    target = _good_target()
    target.pop("decision_history")
    result = SCENARIO.follow_up_check(target)
    assert result["status"] == "not-examined"
    assert result["findings"] == ["decision_history_not_examined"]


def test_finance_fixture_regenerates_deterministically(tmp_path: Path) -> None:
    first = generate_dataset("finance_close", 29, tmp_path / "first")
    second = generate_dataset("finance_close", 29, tmp_path / "second")
    assert first.manifest["fixture_hash"] == second.manifest["fixture_hash"]
    assert (first.gold_dir / "finance_close_reconciliation.json").read_bytes() == (
        SCENARIO.gold_path("reconciliation").read_bytes()
    )


def test_runner_handover_exposes_the_close_source_and_evidence_contract(tmp_path: Path) -> None:
    with RunEnvironment(SCENARIO, _pins(), root=tmp_path) as environment:
        profile = (environment.workspace_dir / "infra-profile.yaml").read_text(encoding="utf-8")
        contract = (environment.workspace_dir / "scenario-evidence-contract.json").read_text(
            encoding="utf-8"
        )
        assert "endpoint_close_entries" in profile
        assert "evidence/finance_close.json" in contract
        assert "total_eur" in contract
