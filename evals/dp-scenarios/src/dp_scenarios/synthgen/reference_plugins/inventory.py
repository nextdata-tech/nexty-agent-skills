"""Independent warehouse-join oracle for inventory-position and rotation."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..reference import ReferenceGold, register_reference_builder


def _inventory_gold(
    data_dir: Path,
    *,
    answer_filename: str,
    diagnostics_filename: str,
    answer_as_bare_rows: bool,
    include_reference_data: bool,
) -> ReferenceGold:
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
    answer = output_rows if answer_as_bare_rows else {"rows": output_rows}
    data_files = (
        {"inventory_position_reference.json": {"rows": output_rows}}
        if include_reference_data
        else {}
    )
    return ReferenceGold(
        files={
            answer_filename: answer,
            diagnostics_filename: diagnostics,
        },
        data_files=data_files,
    )


def _inventory_position_gold(data_dir: Path) -> ReferenceGold:
    """Keep B5's reconciled-row object and reference file byte-for-byte stable."""

    return _inventory_gold(
        data_dir,
        answer_filename="inventory_position_reconciliation.json",
        diagnostics_filename="inventory_position_diagnostics.json",
        answer_as_bare_rows=False,
        include_reference_data=True,
    )


def _inventory_rotation_gold(data_dir: Path) -> ReferenceGold:
    """Return B10 query gold as the bare eight-row result set."""

    return _inventory_gold(
        data_dir,
        answer_filename="inventory_rotation_answer.json",
        diagnostics_filename="inventory_rotation_diagnostics.json",
        answer_as_bare_rows=True,
        include_reference_data=False,
    )


register_reference_builder("inventory_position", _inventory_position_gold)
register_reference_builder("inventory_rotation", _inventory_rotation_gold)
