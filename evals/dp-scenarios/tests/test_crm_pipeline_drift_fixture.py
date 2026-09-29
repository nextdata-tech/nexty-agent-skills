"""Package A contracts for the runner-private B11 CRM source and gold."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from dp_scenarios.mockrest.config import fixture_source_tables, load_config
from dp_scenarios.runner.environment import PinnedVersions, RunEnvironment
from dp_scenarios.scenario import load_scenario
from dp_scenarios.synthgen.datasets import get_dataset
from dp_scenarios.synthgen.defects import _sentinel_for
from dp_scenarios.synthgen.generator import generate_dataset, verify_dataset


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "scenarios/crm-pipeline-drift"
B1 = load_scenario(ROOT / "scenarios/crm-pipeline")
DATASET = "crm_pipeline_drift"
SEED = 29


def _snapshot(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def _source(path: Path, version: str) -> list[dict[str, object]]:
    return json.loads(
        (path / f"source/deals_{version}.json").read_text(encoding="utf-8")
    )


def _gold(path: Path, version: str) -> list[dict[str, object]]:
    return json.loads(
        (path / f"gold/crm_pipeline_drift_{version}.json").read_text(encoding="utf-8")
    )["rows"]


def test_generated_source_matches_b1_then_changes_only_as_specified(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_dataset(DATASET, SEED, first)
    generate_dataset(DATASET, SEED, second)
    assert _snapshot(first) == _snapshot(second)
    assert verify_dataset(first)

    owner_marker = _sentinel_for("owner.email", seed=SEED, dataset=DATASET)
    champion_marker = _sentinel_for("champion.email", seed=SEED, dataset=DATASET)
    assert owner_marker != champion_marker
    b1_response = B1.route_table.routes[0].response
    assert b1_response is not None
    expected_v1 = json.loads(json.dumps(b1_response.data))
    for row in expected_v1:
        if "crm-pii-sentinel-4e2b7f9c" in row["owner"]["email"]:
            row["owner"]["email"] = owner_marker
    v1 = _source(first, "v1")
    v2 = _source(first, "v2")
    assert v1 == expected_v1
    assert len(v1) == 6 and len(v2) == 7
    assert [row["id"] for row in v2] == [
        f"DEAL-{number}" for number in range(2001, 2008)
    ]
    assert all("amount" not in row and "deal_value" in row for row in v2)
    assert all("champion" not in row for row in v1)
    assert [row["id"] for row in v2 if "champion" in row] == ["DEAL-2002", "DEAL-2007"]
    assert {row["champion"]["email"] for row in v2 if "champion" in row} == {
        champion_marker
    }
    assert [row["id"] for row in v2 if row["stage"] == "verbal_commit"] == [
        "DEAL-2002",
        "DEAL-2007",
    ]
    for before, after in zip(v1, v2[:6]):
        expected = {
            "deal_value" if key == "amount" else key: value
            for key, value in before.items()
        }
        if before["id"] == "DEAL-2002":
            expected["stage"] = "verbal_commit"
            expected["champion"] = {
                "name": "Synthetic Champion Two",
                "email": champion_marker,
            }
        assert after == expected
    assert v2[6]["deal_value"] == 31850
    assert v2[6]["updatedAt"] == "2024-01-08T12:00:00+00:00"
    assert sum(row["amount"] for row in v1 if row["status"] == "active") == 171600
    assert sum(row["deal_value"] for row in v2 if row["status"] == "active") == 203450


def test_reference_gold_is_redacted_byte_stable_and_committed(tmp_path: Path) -> None:
    generated = generate_dataset(DATASET, SEED, tmp_path / "fixture")
    b1_gold = json.loads(
        (ROOT / "scenarios/crm-pipeline/gold/crm_pipeline_output.json").read_text(
            encoding="utf-8"
        )
    )
    v1_gold = generated.gold_dir / "crm_pipeline_drift_v1.json"
    assert json.loads(v1_gold.read_text(encoding="utf-8")) == b1_gold
    for version, expected_count, expected_total in (
        ("v1", 5, 171600),
        ("v2", 6, 203450),
    ):
        filename = f"crm_pipeline_drift_{version}.json"
        assert (generated.gold_dir / filename).read_bytes() == (
            PACKAGE / "gold" / filename
        ).read_bytes()
        rows = _gold(generated.out_dir, version)
        assert len(rows) == expected_count
        assert all(
            set(row) == {"deal_id", "stage", "amount", "updated_at"} for row in rows
        )
        assert sum(row["amount"] for row in rows) == expected_total
    assert [
        row["deal_id"]
        for row in _gold(generated.out_dir, "v2")
        if row["stage"] == "verbal_commit"
    ] == ["DEAL-2002", "DEAL-2007"]


def test_route_uses_hidden_sources_and_only_initial_contract_is_visible(
    tmp_path: Path,
) -> None:
    definition = get_dataset(DATASET)
    assert definition.source_tables == ("deals_v1", "deals_v2")
    assert definition.table_columns == {}
    route = load_config(PACKAGE / "route-table.yaml")
    assert fixture_source_tables(route) == frozenset(definition.source_tables)
    deals = route.routes[0]
    b1_deals = B1.route_table.routes[0]
    assert deals.state_family == "crm_deals" and deals.initial_state == "v1"
    assert deals.auth_required == b1_deals.auth_required
    assert deals.pagination == b1_deals.pagination
    assert deals.rate_limit_every == b1_deals.rate_limit_every
    assert route.auth == B1.route_table.auth
    assert route.capability == B1.route_table.capability
    assert [
        (item.path, item.method, item.status, item.write_forbidden)
        for item in route.routes[1:]
    ] == [
        (item.path, item.method, item.status, item.write_forbidden)
        for item in B1.route_table.routes[1:]
    ]

    scenario = replace(B1, fixture=replace(B1.fixture, dataset=DATASET))
    pins = PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1")
    with RunEnvironment(
        scenario, pins, root=tmp_path, route_config=route
    ) as environment:
        manifest = json.loads(
            (environment.fixture_dir / "fixture-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        assert "source_tables" not in manifest
        assert not (environment.fixture_dir / "source").exists()
        assert not (environment.fixture_dir / "gold").exists()
        assert (environment.oracle_dir / "source/deals_v1.json").is_file()
        assert (environment.oracle_dir / "source/deals_v2.json").is_file()
        profile = environment.source_profile_path.read_text(encoding="utf-8")
        for hidden in ("deal_value", "verbal_commit", "champion", "deals_v2"):
            assert hidden not in profile
