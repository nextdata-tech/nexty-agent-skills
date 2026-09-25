"""Independent warehouse-join oracle for the inventory-position scenario."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..reference import ReferenceGold, register_reference_builder


def _inventory_gold(data_dir: Path) -> ReferenceGold:
    warehouses = list(csv.DictReader((data_dir / "warehouses.csv").open(encoding="utf-8", newline="")))
    positions = list(csv.DictReader((data_dir / "inventory_positions.csv").open(encoding="utf-8", newline="")))
    lookup = {row["warehouse_id"]: row for row in warehouses}
    output_rows: list[dict[str, Any]] = []
    orphan_ids: set[str] = set()
    negative_ids: list[str] = []
    orphan_position_count = 0
    for row in positions:
        warehouse_id = row["warehouse_id"]
        quantity = int(Decimal(row["quantity"]))
        warehouse = lookup.get(warehouse_id)
        quality = "valid"
        if warehouse is None:
            quality = "orphan_warehouse"
            orphan_ids.add(warehouse_id)
            orphan_position_count += 1
        if quantity < 0:
            quality = "negative_stock" if quality == "valid" else "orphan_and_negative"
            negative_ids.append(row["position_id"])
        output_rows.append(
            {
                "position_id": row["position_id"],
                "sku": row["sku"],
                "warehouse_id": warehouse_id,
                "region": warehouse["region"] if warehouse is not None else None,
                "quantity": quantity,
                "quality": quality,
            }
        )
    diagnostics = {
        "input_position_count": len(positions),
        "warehouse_count": len(warehouses),
        "orphan_warehouse_count": orphan_position_count,
        "orphan_warehouse_ids": sorted(orphan_ids),
        "negative_quantity_count": len(negative_ids),
        "negative_position_ids": sorted(negative_ids),
        "quality_policy": "warn_and_preserve",
    }
    reconciliation = {"rows": output_rows}
    return ReferenceGold(
        files={
            "inventory_position_reconciliation.json": reconciliation,
            "inventory_position_diagnostics.json": diagnostics,
        },
        data_files={"inventory_position_reference.json": reconciliation},
    )


register_reference_builder("inventory_position", _inventory_gold)
