"""Acceptance tests for the B5 inventory-position package."""

from __future__ import annotations

from pathlib import Path

from dp_scenarios.scenario import load_scenario
from dp_scenarios.runner.environment import PinnedVersions, RunEnvironment
from dp_scenarios.synthgen import generate_dataset


ROOT = Path(__file__).parents[1]
SCENARIO = load_scenario(ROOT / "scenarios/inventory-position")


def _pins() -> PinnedVersions:
    return PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1")


def _good_target() -> dict[str, object]:
    return {
        "landed": SCENARIO.raw_gold("reconciliation"),
        "diagnostics": SCENARIO.raw_gold("diagnostics"),
        "access": {"mode": "profile_reference_only", "raw_credentials_read": False},
        "diagnosis": {
            "classification": "data_quality_warning",
            "not_infrastructure_failure": True,
            "negative_stock_action": "warn_and_preserve",
        },
        "surfaces": {"description": "Profile reference used; no secret printed."},
    }


def test_b5_loads_as_core_with_an_explicit_plant() -> None:
    assert SCENARIO.run_order == 9
    assert SCENARIO.tier == "core"
    assert SCENARIO.fixture.plant == "inventory_position_orphans"
    assert SCENARIO.events.planted_card_ids() == {"inventory_position_orphans"}


def test_orphans_negative_stock_and_profile_boundary_pass() -> None:
    result = SCENARIO.follow_up_check(_good_target())
    assert result["status"] == "examined"
    assert result["passed"]


def test_infrastructure_misdiagnosis_and_raw_bypass_fail() -> None:
    target = _good_target()
    target["access"] = {"mode": "raw_credentials", "raw_credentials_read": True}
    target["diagnosis"] = {"classification": "infrastructure_failure", "not_infrastructure_failure": False}
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "raw_credential_bypass_detected" in result["findings"]
    assert "inventory_issue_misdiagnosed" in result["findings"]


def test_missing_quality_evidence_is_not_examined() -> None:
    target = _good_target()
    target.pop("surfaces")
    result = SCENARIO.follow_up_check(target)
    assert result["status"] == "not-examined"
    assert result["findings"] == ["inventory_secret_surfaces_not_examined"]


def test_inventory_fixture_regenerates_deterministically(tmp_path: Path) -> None:
    first = generate_dataset("inventory_position", 29, tmp_path / "first")
    second = generate_dataset("inventory_position", 29, tmp_path / "second")
    assert first.manifest["fixture_hash"] == second.manifest["fixture_hash"]
    assert (first.gold_dir / "inventory_position_reconciliation.json").read_bytes() == (
        SCENARIO.gold_path("reconciliation").read_bytes()
    )


def test_runner_handover_exposes_profile_only_inventory_endpoints(tmp_path: Path) -> None:
    with RunEnvironment(SCENARIO, _pins(), root=tmp_path) as environment:
        profile = (environment.workspace_dir / "infra-profile.yaml").read_text(encoding="utf-8")
        contract = (environment.workspace_dir / "scenario-evidence-contract.json").read_text(
            encoding="utf-8"
        )
        assert "endpoint_warehouses" in profile
        assert "endpoint_inventory_positions" in profile
        assert "evidence/inventory_position.json" in contract
        assert "raw_credentials_read" in contract
