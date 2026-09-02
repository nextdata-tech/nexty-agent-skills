"""Seeded source definitions for the two smoke-tier scenario datasets.

The definitions own the fixed epoch-relative base instants, source schemas,
and declarative defect plans.  Builders receive the one seeded RNG created by
the generator, so no timestamp or value depends on the current clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import random
from typing import Any, Callable, Mapping

from .defects import Frame

BASE_INSTANT = "2024-01-01T00:00:00+00:00"
_BASE_DATETIME = datetime.fromisoformat(BASE_INSTANT)
if _BASE_DATETIME.tzinfo is None or _BASE_DATETIME.utcoffset() != timedelta(0):
    raise ValueError("BASE_INSTANT must carry an explicit UTC offset")


@dataclass(frozen=True)
class InjectorSpec:
    """A defect name, target table, and JSON-compatible parameters."""

    table: str
    name: str
    parameters: Mapping[str, Any]
    parent_table: str | None = None


@dataclass(frozen=True)
class DatasetDefinition:
    """Complete deterministic contract for one generated dataset."""

    name: str
    base_instant: str
    table_columns: Mapping[str, tuple[str, ...]]
    injectors: tuple[InjectorSpec, ...]
    builder: Callable[[int, random.Random], Mapping[str, Frame]]
    description: str


def _timestamp(base: datetime, *, days: int, hours: int) -> str:
    return (base + timedelta(days=days, hours=hours)).isoformat(timespec="seconds")


def _build_grain_trap(seed: int, rng: random.Random) -> Mapping[str, Frame]:
    """Build the parent-child-grain-trap source with deliberately varying child counts.

    Gold includes rows whose order status is ``active`` and whose line item
    joins to that order by exact ``order_id``.  It excludes tombstoned orders
    and true orphan line items; the control total is the active-order amount
    sum before any line-item fan-out.
    """

    base = _BASE_DATETIME
    regions = ("north", "south", "east", "west")
    orders: Frame = []
    line_items: Frame = []
    order_number = 1
    line_number = 1
    for region_index, region in enumerate(regions):
        for local_index in range(5):
            order_id = f"ORD-{seed}-{order_number:03d}"
            orders.append(
                {
                    "order_id": order_id,
                    "region": region,
                    "order_timestamp": _timestamp(
                        base,
                        days=region_index * 12 + local_index * 2,
                        hours=rng.randrange(0, 12),
                    ),
                    # The slope makes the trap robust for the shipped seed sweep;
                    # injectors still make this an empirical property, not a
                    # structural guarantee for every possible seed.
                    "order_amount": Decimal(
                        5000 * (region_index + 1)
                        + 10000 * (local_index + 1)
                        + rng.randrange(0, 100)
                    ) / Decimal("100"),
                    "status": "active",
                }
            )
            for child_index in range(local_index + 1):
                line_items.append(
                    {
                        "line_item_id": f"LINE-{seed}-{line_number:04d}",
                        "order_id": order_id,
                        "product": f"product-{(region_index * 5 + local_index + child_index) % 11:02d}",
                        "quantity": 1 + rng.randrange(1, 5),
                        "unit_price": Decimal(
                            750 + region_index * 125 + local_index * 40 + rng.randrange(0, 20)
                        )
                        / Decimal("100"),
                    }
                )
                line_number += 1
            order_number += 1
    return {"orders": orders, "line_items": line_items}


def _build_zero_row_optional(seed: int, rng: random.Random) -> Mapping[str, Frame]:
    """Build required records and a valid, period-empty optional collection.

    The primary resource has five rows for the seeded period. This file-backed
    smoke variant deliberately emits the optional CSV with its valid header and
    no rows. A REST-shaped 200/empty-array variant belongs to the mock REST
    scenario so the two resource semantics remain explicit.
    """

    base = _BASE_DATETIME
    primary: Frame = []
    for index in range(5):
        primary.append(
            {
                "record_id": f"REC-{seed}-{index + 1:03d}",
                "period": "2024-01",
                "record_timestamp": _timestamp(base, days=index, hours=rng.randrange(0, 24)),
                "value": Decimal(1000 + seed % 100 + index * 125 + rng.randrange(0, 25))
                / Decimal("100"),
                "customer_name": f"Customer {index + 1}",
                "customer_email": f"customer-{index + 1}@example.invalid",
                "salary": f"salary-{index + 1}",
            }
        )
    # The schema is present and valid, but no event falls in the selected
    # period.  This is an empty collection, not a failed or missing resource.
    optional: Frame = []
    return {"primary": primary, "optional_events": optional}


DATASET_DEFINITIONS: Mapping[str, DatasetDefinition] = {
    "grain_trap": DatasetDefinition(
        name="grain_trap",
        base_instant=BASE_INSTANT,
        table_columns={
            "orders": (
                "order_id",
                "region",
                "order_timestamp",
                "order_amount",
                "status",
            ),
            "line_items": (
                "line_item_id",
                "order_id",
                "product",
                "quantity",
                "unit_price",
            ),
        },
        injectors=(
            InjectorSpec(
                "line_items",
                "orphan_foreign_keys",
                {"count": 3},
                parent_table="orders",
            ),
            InjectorSpec("orders", "tombstones", {"rate": 0.10}),
            InjectorSpec("line_items", "pii_sentinels", {"columns": ["product"]}),
        ),
        builder=_build_grain_trap,
        description=(
            "Orders have one through five line items. Gold includes active orders "
            "only; the exact inner join excludes tombstoned orders and orphan line "
            "items. The control total is the active-order revenue sum."
        ),
    ),
    "zero_row_optional": DatasetDefinition(
        name="zero_row_optional",
        base_instant=BASE_INSTANT,
        table_columns={
            "primary": (
                "record_id",
                "period",
                "record_timestamp",
                "value",
                "customer_name",
                "customer_email",
                "salary",
            ),
            "optional_events": ("event_id", "record_id", "event_timestamp"),
        },
        injectors=(
            InjectorSpec(
                "primary",
                "pii_sentinels",
                {"columns": ["customer_name", "customer_email", "salary"]},
            ),
        ),
        builder=_build_zero_row_optional,
        description=(
            "Primary has five required January records. The file-backed smoke "
            "variant deliberately emits optional_events.csv with only its valid "
            "header and zero rows; a REST-shaped 200/empty-array version belongs "
            "to the mock REST scenario. Gold therefore requires exactly zero "
            "optional rows."
        ),
    ),
}

# Short plural alias for callers that treat the definitions as a registry.
DATASETS = DATASET_DEFINITIONS


def get_dataset(name: str) -> DatasetDefinition:
    """Return a named dataset definition or raise a useful error."""

    try:
        return DATASET_DEFINITIONS[name]
    except KeyError as exc:
        available = ", ".join(sorted(DATASET_DEFINITIONS))
        raise ValueError(f"unknown dataset {name!r}; choose one of: {available}") from exc


def build_tables(name: str, seed: int, rng: random.Random) -> Mapping[str, Frame]:
    """Build un-injected source tables with the caller's seeded generator."""

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    definition = get_dataset(name)
    return definition.builder(seed, rng)


__all__ = [
    "BASE_INSTANT",
    "DATASETS",
    "DATASET_DEFINITIONS",
    "DatasetDefinition",
    "InjectorSpec",
    "build_tables",
    "get_dataset",
]
