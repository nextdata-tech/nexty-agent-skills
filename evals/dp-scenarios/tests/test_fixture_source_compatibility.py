"""Pre-change fixture and route digest pins for scenarios without source tables."""

from __future__ import annotations

import json
from pathlib import Path

from dp_scenarios.runner.environment import _mock_route_config_digest
from dp_scenarios.scenario import load_scenarios


SCENARIOS = Path(__file__).parents[1] / "scenarios"
PRE_SOURCE_MANIFEST_KEYS = frozenset(
    {
        "applied_injectors",
        "base_instant",
        "dataset",
        "description",
        "file_hashes",
        "fixture_hash",
        "format_version",
        "mutation",
        "pii_dictionary",
        "pii_markers",
        "planted_orphan_values",
        "python_implementation",
        "python_version",
        "seed",
        "table_row_counts",
    }
)
PRE_SOURCE_FIXTURE_HASHES = {
    "application-reconciliation": "419a620b11719595a5838012aff310dd4c54dbae5aee865e9f4b0fa245f5f10e",
    "capability-shortfall": "7c329774d54bba0551e23a88f6a1439da2f569e91026db674a01ecc1d5432c0a",
    "credential-rotation": "7c329774d54bba0551e23a88f6a1439da2f569e91026db674a01ecc1d5432c0a",
    "crm-pipeline": "6b03043c69f1303fff27af451d518590d1d376a511802963c99c87eedf8d7c5c",
    "finance-close": "81173495792c13c82b62220345513eaaad8f8d795ff33603d2d87657d49803d0",
    "inventory-position": "7543585008de404b91072cb6cb937ac2543a1c9183c657004f8b45c07bc9eff4",
    "locale-timezone": "9d5e4eb52f2fe6ff0a857915e93fa0568106293925287c5ed35027ef0b1ab709",
    "marketing-attribution": "814423d1b10aafb06122686fe77198981c32eac3ba2cd3d86789068e44bbf58a",
    "parent-child-grain-trap": "7c329774d54bba0551e23a88f6a1439da2f569e91026db674a01ecc1d5432c0a",
    "restart-and-switch": "7c329774d54bba0551e23a88f6a1439da2f569e91026db674a01ecc1d5432c0a",
    "sigterm-diagnosis": "7c329774d54bba0551e23a88f6a1439da2f569e91026db674a01ecc1d5432c0a",
    "zero-row-optional-output": "2fb6321348f80d9e192c2eec36d47a507f3b890fa3efe1cd2d8b9f0a0fdbdde1",
}
PRE_SOURCE_ROUTE_DIGESTS = {
    "capability-shortfall": "e1190f5a59f79e2528f50d1dd49b0fa44729e47ad60e6ac9105db9f4503cbf69",
    "crm-pipeline": "522bf40aa22e2200920fd6f092ec2d9cb7a2a0df5bd6ab682fdbedcd927868b5",
    "finance-close": "898220678f390e3df6d10377e042833b94cee522619ac27f723dc5290014ea03",
    "inventory-position": "5683c14f1785992f9c29df3a546e850f0a3bd3f32e1a471dfb31aa3079cc35bc",
}


def _snapshot(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_all_shipped_scenario_fixtures_and_routes_keep_their_prechange_bytes(
    tmp_path: Path,
) -> None:
    # Every scenario that shipped before source tables must still ship with its
    # original bytes. Scenarios added later are not pinned here; they only have
    # to generate deterministically.
    scenarios = load_scenarios(SCENARIOS)
    assert set(PRE_SOURCE_FIXTURE_HASHES) <= {scenario.id for scenario in scenarios}
    pinned_route_scenarios = {
        scenario.id
        for scenario in scenarios
        if scenario.route_table is not None and scenario.id in PRE_SOURCE_FIXTURE_HASHES
    }
    assert pinned_route_scenarios == set(PRE_SOURCE_ROUTE_DIGESTS)

    for scenario in scenarios:
        first = scenario.generate_fixture(tmp_path / scenario.id / "first")
        second = scenario.generate_fixture(tmp_path / scenario.id / "second")
        assert _snapshot(first.out_dir) == _snapshot(second.out_dir), scenario.id
        if scenario.id not in PRE_SOURCE_FIXTURE_HASHES:
            continue
        manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
        assert frozenset(manifest) == PRE_SOURCE_MANIFEST_KEYS, scenario.id
        assert manifest["fixture_hash"] == PRE_SOURCE_FIXTURE_HASHES[scenario.id], scenario.id
        if scenario.route_table is not None:
            assert _mock_route_config_digest(scenario.route_table) == PRE_SOURCE_ROUTE_DIGESTS[
                scenario.id
            ]
