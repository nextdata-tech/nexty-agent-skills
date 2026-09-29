"""Inventory positions and warehouse lookup rows for B5 and B10."""

from __future__ import annotations

from decimal import Decimal
import random
from typing import Mapping

from ..datasets import BASE_INSTANT, DatasetDefinition, InjectorSpec
from ..defects import Frame
from ..registry import register_dataset


_INVENTORY_TABLE_COLUMNS = {
    "warehouses": ("warehouse_id", "region", "label"),
    "inventory_positions": (
        "position_id",
        "sku",
        "warehouse_id",
        "quantity",
        "as_of",
        "status",
        "notes",
    ),
}
_INVENTORY_INJECTORS = (
    InjectorSpec(
        "inventory_positions",
        "orphan_foreign_keys",
        {"count": 2},
        parent_table="warehouses",
    ),
    InjectorSpec("inventory_positions", "negative_values", {"column": "quantity", "count": 1}),
)


def _build_inventory(seed: int, rng: random.Random) -> Mapping[str, Frame]:
    """Build stable positions; injectors add two orphan IDs and one negative."""

    del rng
    warehouses: Frame = [
        {"warehouse_id": "WH-01", "region": "north", "label": "North Hub"},
        {"warehouse_id": "WH-02", "region": "south", "label": "South Hub"},
        {"warehouse_id": "WH-03", "region": "east", "label": "East Hub"},
    ]
    positions: Frame = [
        {
            "position_id": f"POS-{seed}-{index:03d}",
            "sku": f"SKU-{index:03d}",
            "warehouse_id": warehouse,
            "quantity": Decimal(quantity),
            "as_of": "2024-01-31",
            "status": "posted",
            "notes": "inventory position",
        }
        for index, (warehouse, quantity) in enumerate(
            (("WH-01", 12), ("WH-02", 7), ("WH-03", 4), ("WH-01", 8),
             ("WH-02", 15), ("WH-03", 3), ("WH-01", 11), ("WH-02", 6)),
            start=1,
        )
    ]
    return {"warehouses": warehouses, "inventory_positions": positions}


def _register_inventory_variant(*, name: str, description: str, plant: str) -> None:
    register_dataset(
        DatasetDefinition(
            name=name,
            base_instant=BASE_INSTANT,
            table_columns=_INVENTORY_TABLE_COLUMNS,
            injectors=_INVENTORY_INJECTORS,
            builder=_build_inventory,
            description=description,
            plant=plant,
            requires_explicit_plant=True,
        )
    )


_register_inventory_variant(
    name="inventory_position",
    description=(
        "Inventory positions join to warehouse lookup rows, with two planted "
        "orphan warehouse identifiers and one negative stock position."
    ),
    plant="inventory_position_orphans",
)
_register_inventory_variant(
    name="inventory_rotation",
    description=(
        "Inventory positions join to warehouse lookup rows, with two planted "
        "orphan warehouse identifiers and one negative stock position for the "
        "B10 revoked-window rotation scenario."
    ),
    plant="B10-revoked-window",
)
