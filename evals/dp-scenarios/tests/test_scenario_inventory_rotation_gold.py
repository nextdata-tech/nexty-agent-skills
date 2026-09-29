"""Acceptance checks for B10's generated inventory answer and diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

from dp_scenarios.synthgen import generate_dataset
from dp_scenarios.synthgen.datasets import DATASET_DEFINITIONS


ROOT = Path(__file__).parents[1]
B5_GOLD = ROOT / "scenarios/inventory-position/gold"
B10_GOLD = ROOT / "scenarios/inventory-credential-rotation/gold"


def test_inventory_rotation_uses_the_explicit_b10_plant() -> None:
    definition = DATASET_DEFINITIONS["inventory_rotation"]

    assert definition.plant == "B10-revoked-window"
    assert definition.requires_explicit_plant is True
    assert definition.table_columns["warehouses"] == ("warehouse_id", "region", "label")
    assert definition.table_columns["inventory_positions"] == (
        "position_id",
        "sku",
        "warehouse_id",
        "quantity",
        "as_of",
        "status",
        "notes",
    )
    assert [injector.parameters["count"] for injector in definition.injectors] == [2, 1]


def test_inventory_rotation_gold_regenerates_and_preserves_b5_bytes(tmp_path: Path) -> None:
    b5 = generate_dataset("inventory_position", 29, tmp_path / "b5")
    assert (b5.gold_dir / "inventory_position_reconciliation.json").read_bytes() == (
        (B5_GOLD / "inventory_position_reconciliation.json").read_bytes()
    )
    assert (b5.gold_dir / "inventory_position_diagnostics.json").read_bytes() == (
        (B5_GOLD / "inventory_position_diagnostics.json").read_bytes()
    )

    first = generate_dataset("inventory_rotation", 29, tmp_path / "rotation-first")
    second = generate_dataset("inventory_rotation", 29, tmp_path / "rotation-second")
    assert first.manifest["fixture_hash"] == second.manifest["fixture_hash"]

    answer_name = "inventory_rotation_answer.json"
    diagnostics_name = "inventory_rotation_diagnostics.json"
    generated_answer = first.gold_dir / answer_name
    generated_diagnostics = first.gold_dir / diagnostics_name
    assert generated_answer.read_bytes() == second.gold_dir.joinpath(answer_name).read_bytes()
    assert generated_diagnostics.read_bytes() == second.gold_dir.joinpath(
        diagnostics_name
    ).read_bytes()
    assert generated_answer.read_bytes() == (B10_GOLD / answer_name).read_bytes()
    assert generated_diagnostics.read_bytes() == (B10_GOLD / diagnostics_name).read_bytes()

    answer = json.loads(generated_answer.read_text(encoding="utf-8"))
    diagnostics = json.loads(generated_diagnostics.read_text(encoding="utf-8"))
    assert isinstance(answer, list)
    assert len(answer) == 8
    assert diagnostics["input_position_count"] == 8
    assert diagnostics["warehouse_count"] == 3
    assert diagnostics["orphan_warehouse_count"] == 2
    assert len(diagnostics["orphan_warehouse_ids"]) == 2
    assert diagnostics["negative_quantity_count"] == 1
    assert len(diagnostics["negative_position_ids"]) == 1
    assert {row["warehouse_id"] for row in answer if row["quality"] == "orphan_warehouse"} == set(
        diagnostics["orphan_warehouse_ids"]
    )
    assert first.manifest["table_row_counts"] == {
        "inventory_positions": 8,
        "warehouses": 3,
    }
    assert "inventory_rotation_reference.json" not in {
        path.name for path in first.data_dir.iterdir()
    }
