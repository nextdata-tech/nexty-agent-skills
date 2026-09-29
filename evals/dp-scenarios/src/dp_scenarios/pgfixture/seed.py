"""Deterministic source data for the live Postgres fixture.

Two datasets are supported:

``grain_trap`` (the default, unchanged since before this module supported a
``dataset`` argument) reuses the existing synthgen ``grain_trap`` dataset for
the core ``credential-rotation`` scenario.  Its source, gold, table DDL, and
probe-table shape are byte-identical to what this module produced before B10.

``inventory_rotation`` is the W1 dataset registered for the B10
``inventory-credential-rotation`` scenario (warehouses/inventory_positions,
plant ``B10-revoked-window``).  Both of its planted defects (two orphan
warehouse ids, one negative quantity) are applied by synthgen's own injectors,
unlike ``grain_trap`` which gets its negative-quantity defect from a manual
post-generation injection kept for backward compatibility.

Each dataset also carries its own least-privilege "probe table": a small
lookup-schema table, invisible to `information_schema` but visible in
`pg_catalog`, that the fixture uses to prove catalog-vs-query-access
separation.  Its name, DDL, and row shape are dataset-specific and carried on
`SeededData` so `pgfixture.fixture` can create it generically.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal
import json
from pathlib import Path
import random
from types import MappingProxyType
from typing import Any, Mapping

from dp_scenarios.synthgen.defects import Frame, negative_values
from dp_scenarios.synthgen.generator import generate_dataset


DATASET_GRAIN_TRAP = "grain_trap"
DATASET_INVENTORY_ROTATION = "inventory_rotation"
SUPPORTED_DATASETS = (DATASET_GRAIN_TRAP, DATASET_INVENTORY_ROTATION)

# Backward-compatible alias: this was the only dataset before B10's `dataset`
# argument existed, and remains the default.
DATASET = DATASET_GRAIN_TRAP

NEGATIVE_QUANTITY_COUNT = 3
_NEGATIVE_RNG_SALT = 104_729

_GRAIN_TRAP_TABLE_DDL = MappingProxyType(
    {
        "orders": (
            "order_id text NOT NULL, region text NOT NULL, "
            "order_timestamp timestamptz NOT NULL, order_amount numeric(18,2) NOT NULL, "
            "status text NOT NULL"
        ),
        "line_items": (
            "line_item_id text NOT NULL, order_id text NOT NULL, product text NOT NULL, "
            "quantity integer NOT NULL, unit_price numeric(18,2) NOT NULL"
        ),
    }
)
_GRAIN_TRAP_PROBE_TABLE = "product_catalog"
_GRAIN_TRAP_PROBE_DDL = (
    "product text PRIMARY KEY, category text NOT NULL, reference_price numeric(18,2) NOT NULL"
)

_INVENTORY_ROTATION_TABLE_DDL = MappingProxyType(
    {
        "warehouses": "warehouse_id text NOT NULL, region text NOT NULL, label text NOT NULL",
        "inventory_positions": (
            "position_id text NOT NULL, sku text NOT NULL, warehouse_id text NOT NULL, "
            "quantity integer NOT NULL, as_of date NOT NULL, status text NOT NULL, "
            "notes text NOT NULL"
        ),
    }
)
_INVENTORY_ROTATION_PROBE_TABLE = "warehouse_directory"
_INVENTORY_ROTATION_PROBE_DDL = (
    "warehouse_id text PRIMARY KEY, manager text NOT NULL, note text NOT NULL"
)


@dataclass(frozen=True)
class SeededData:
    """The source rows, gold rows, and defect ledger for one scenario seed."""

    seed: int
    source_dir: Path
    tables: Mapping[str, tuple[Mapping[str, Any], ...]]
    lookup_rows: tuple[Mapping[str, Any], ...]
    gold_rows: tuple[Mapping[str, Any], ...]
    gold_files: Mapping[str, Any]
    manifest: Mapping[str, Any]
    injection_records: tuple[Mapping[str, Any], ...]
    dataset: str = DATASET_GRAIN_TRAP
    primary_table: str = "line_items"
    table_ddl: Mapping[str, str] = field(default_factory=lambda: _GRAIN_TRAP_TABLE_DDL)
    probe_table: str = _GRAIN_TRAP_PROBE_TABLE
    probe_ddl: str = _GRAIN_TRAP_PROBE_DDL

    @property
    def orphan_count(self) -> int:
        """Return the number of planted orphan foreign keys."""

        return sum(
            int(record.get("changed_rows", 0))
            for record in self.injection_records
            if record.get("name") == "orphan_foreign_keys"
        )

    @property
    def negative_quantity_count(self) -> int:
        """Return the number of planted negative quantities."""

        return sum(
            int(record.get("changed_rows", 0))
            for record in self.injection_records
            if record.get("name") == "negative_values"
            and record.get("target_table") == self.primary_table
        )


def _read_typed_rows(path: Path, table: str) -> Frame:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if table == "orders":
        for row in rows:
            row["order_amount"] = Decimal(row["order_amount"])
    elif table == "line_items":
        for row in rows:
            row["quantity"] = int(row["quantity"])
            row["unit_price"] = Decimal(row["unit_price"])
    else:
        raise ValueError(f"unknown seeded table: {table}")
    return rows


def _lookup_rows(line_items: Frame) -> tuple[Mapping[str, Any], ...]:
    """Build a small hidden lookup table from the same generated source."""

    products: dict[str, Decimal] = {}
    for row in line_items:
        product = str(row["product"])
        products.setdefault(product, Decimal(row["unit_price"]))
    return tuple(
        {
            "product": product,
            "category": f"category-{index % 4}",
            "reference_price": price,
        }
        for index, (product, price) in enumerate(sorted(products.items()))
    )


def _read_typed_inventory_rotation_rows(path: Path, table: str) -> Frame:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if table == "inventory_positions":
        for row in rows:
            row["quantity"] = int(Decimal(row["quantity"]))
    elif table != "warehouses":
        raise ValueError(f"unknown seeded table: {table}")
    return rows


def _inventory_rotation_probe_rows(warehouses: Frame) -> tuple[Mapping[str, Any], ...]:
    """Build a small hidden probe table unrelated to the queryable inventory."""

    ordered = sorted(warehouses, key=lambda row: str(row["warehouse_id"]))
    return tuple(
        {
            "warehouse_id": str(row["warehouse_id"]),
            "manager": f"manager-{index}",
            "note": "internal warehouse directory",
        }
        for index, row in enumerate(ordered)
    )


def _seed_grain_trap(seed: int, destination: Path) -> SeededData:
    """Materialize the ``grain_trap`` rows and gold data under ``destination``.

    ``generate_dataset`` owns the parent-child-grain-trap source, orphan-FK defect, and
    reference implementation.  The additional negative-quantity injector is
    deliberately applied to typed rows after CSV generation, so the data sent
    to Postgres is the exact in-memory source described by this result.
    """

    generated = generate_dataset(DATASET_GRAIN_TRAP, seed, destination / "synthgen")
    orders = _read_typed_rows(generated.data_dir / "orders.csv", "orders")
    line_items = _read_typed_rows(generated.data_dir / "line_items.csv", "line_items")

    line_items, negative_record = negative_values(
        "quantity", NEGATIVE_QUANTITY_COUNT
    )(line_items, random.Random(seed + _NEGATIVE_RNG_SALT))
    manifest = json.loads(generated.manifest_path.read_text(encoding="utf-8"))
    records: list[Mapping[str, Any]] = []
    for item in manifest["applied_injectors"]:
        changed = dict(item["changed"])
        records.append(
            MappingProxyType(
                {
                    "target_table": item["target_table"],
                    "name": item["name"],
                    "parameters": dict(item["parameters"]),
                    **changed,
                }
            )
        )
    records.append(
        MappingProxyType(
            {
                "target_table": "line_items",
                "name": negative_record.name,
                **negative_record.to_dict(),
            }
        )
    )

    gold_files: dict[str, Any] = {}
    for path in sorted(generated.gold_dir.glob("*.json")):
        gold_files[path.name] = json.loads(path.read_text(encoding="utf-8"))
    gold_value = gold_files.get("grain_trap_by_region.json")
    if not isinstance(gold_value, list) or not gold_value:
        raise ValueError("synthgen did not emit a non-empty parent-child-grain-trap gold row-set")

    tables = MappingProxyType(
        {
            "orders": tuple(MappingProxyType(dict(row)) for row in orders),
            "line_items": tuple(MappingProxyType(dict(row)) for row in line_items),
        }
    )
    return SeededData(
        seed=seed,
        source_dir=generated.data_dir,
        tables=tables,
        lookup_rows=_lookup_rows(line_items),
        gold_rows=tuple(MappingProxyType(dict(row)) for row in gold_value),
        gold_files=MappingProxyType(gold_files),
        manifest=MappingProxyType(manifest),
        injection_records=tuple(records),
        dataset=DATASET_GRAIN_TRAP,
        primary_table="line_items",
        table_ddl=_GRAIN_TRAP_TABLE_DDL,
        probe_table=_GRAIN_TRAP_PROBE_TABLE,
        probe_ddl=_GRAIN_TRAP_PROBE_DDL,
    )


def _seed_inventory_rotation(seed: int, destination: Path) -> SeededData:
    """Materialize the B10 ``inventory_rotation`` rows and gold data.

    Unlike ``grain_trap``, both planted defects (two orphan warehouse ids, one
    negative quantity) are synthgen injectors declared on the
    ``inventory_rotation`` dataset itself (see
    ``synthgen/dataset_plugins/inventory.py``), so no manual post-generation
    injection is needed here.
    """

    generated = generate_dataset(DATASET_INVENTORY_ROTATION, seed, destination / "synthgen")
    warehouses = _read_typed_inventory_rotation_rows(
        generated.data_dir / "warehouses.csv", "warehouses"
    )
    positions = _read_typed_inventory_rotation_rows(
        generated.data_dir / "inventory_positions.csv", "inventory_positions"
    )
    manifest = json.loads(generated.manifest_path.read_text(encoding="utf-8"))
    records: list[Mapping[str, Any]] = []
    for item in manifest["applied_injectors"]:
        changed = dict(item["changed"])
        records.append(
            MappingProxyType(
                {
                    "target_table": item["target_table"],
                    "name": item["name"],
                    "parameters": dict(item["parameters"]),
                    **changed,
                }
            )
        )

    gold_files: dict[str, Any] = {}
    for path in sorted(generated.gold_dir.glob("*.json")):
        gold_files[path.name] = json.loads(path.read_text(encoding="utf-8"))
    gold_value = gold_files.get("inventory_rotation_answer.json")
    if not isinstance(gold_value, list) or not gold_value:
        raise ValueError("synthgen did not emit a non-empty inventory_rotation gold row-set")

    tables = MappingProxyType(
        {
            "warehouses": tuple(MappingProxyType(dict(row)) for row in warehouses),
            "inventory_positions": tuple(MappingProxyType(dict(row)) for row in positions),
        }
    )
    return SeededData(
        seed=seed,
        source_dir=generated.data_dir,
        tables=tables,
        lookup_rows=_inventory_rotation_probe_rows(warehouses),
        gold_rows=tuple(MappingProxyType(dict(row)) for row in gold_value),
        gold_files=MappingProxyType(gold_files),
        manifest=MappingProxyType(manifest),
        injection_records=tuple(records),
        dataset=DATASET_INVENTORY_ROTATION,
        primary_table="inventory_positions",
        table_ddl=_INVENTORY_ROTATION_TABLE_DDL,
        probe_table=_INVENTORY_ROTATION_PROBE_TABLE,
        probe_ddl=_INVENTORY_ROTATION_PROBE_DDL,
    )


def seed_inventory(seed: int, work_dir: str | Path, *, dataset: str = DATASET) -> SeededData:
    """Materialize deterministic rotation-scenario rows and gold data under ``work_dir``.

    ``dataset`` selects between the original ``grain_trap`` source (the
    default, byte-compatible with every caller that predates this argument)
    and the B10 ``inventory_rotation`` source.
    """

    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    destination = Path(work_dir)
    if dataset == DATASET_GRAIN_TRAP:
        return _seed_grain_trap(seed, destination)
    if dataset == DATASET_INVENTORY_ROTATION:
        return _seed_inventory_rotation(seed, destination)
    raise ValueError(
        f"unsupported pgfixture dataset {dataset!r}; expected one of {SUPPORTED_DATASETS!r}"
    )


__all__ = [
    "DATASET",
    "DATASET_GRAIN_TRAP",
    "DATASET_INVENTORY_ROTATION",
    "NEGATIVE_QUANTITY_COUNT",
    "SUPPORTED_DATASETS",
    "SeededData",
    "seed_inventory",
]
