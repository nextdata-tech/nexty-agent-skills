"""Deterministic source data for the live Postgres fixture.

The existing synthgen ``grain_trap`` dataset supplies the source tables and
independent gold reference.  B5 adds its quantity defect through the public
synthgen injector, keeping the source and every planted defect tied to the
scenario seed without committing a large CSV fixture.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
import random
from types import MappingProxyType
from typing import Any, Mapping

from dp_scenarios.synthgen.defects import Frame, InjectionRecord, negative_values
from dp_scenarios.synthgen.generator import generate_dataset


DATASET = "grain_trap"
NEGATIVE_QUANTITY_COUNT = 3
_NEGATIVE_RNG_SALT = 104_729


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
            and record.get("target_table") == "line_items"
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


def seed_inventory(seed: int, work_dir: str | Path) -> SeededData:
    """Materialize deterministic B5 rows and gold data under ``work_dir``.

    ``generate_dataset`` owns the grain-trap source, orphan-FK defect, and
    reference implementation.  The additional negative-quantity injector is
    deliberately applied to typed rows after CSV generation, so the data sent
    to Postgres is the exact in-memory source described by this result.
    """

    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    destination = Path(work_dir)
    generated = generate_dataset(DATASET, seed, destination / "synthgen")
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
        raise ValueError("synthgen did not emit a non-empty grain-trap gold row-set")

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
    )


__all__ = ["DATASET", "NEGATIVE_QUANTITY_COUNT", "SeededData", "seed_inventory"]
