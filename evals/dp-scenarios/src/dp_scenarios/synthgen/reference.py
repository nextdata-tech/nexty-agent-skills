"""Independent SQL gold calculator for generated source files.

This module deliberately imports only standard-library CSV/SQL utilities.  It
reads generated source files as an external oracle and has no dependency on
the dataset builders, defect injectors, or any data-product implementation.
The explicit SQL filters make tombstone and orphan handling part of the gold
contract instead of an accidental side effect of a join.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
import importlib
import inspect
import json
from pathlib import Path
import pkgutil
import sqlite3
import threading
from typing import Any, Mapping


ReferenceBuilder = Any
_REFERENCE_BUILDERS: dict[str, ReferenceBuilder] = {}
_REFERENCE_PLUGINS_DISCOVERED = False
_REFERENCE_DISCOVERY_LOCK = threading.Lock()


def register_reference_builder(dataset_name: str, builder: ReferenceBuilder) -> ReferenceBuilder:
    """Register an additive independent reference builder."""

    if not isinstance(dataset_name, str) or not dataset_name:
        raise ValueError("reference builder dataset name must be non-empty")
    if not callable(builder):
        raise TypeError("reference builder must be callable")
    if dataset_name in _REFERENCE_BUILDERS:
        raise ValueError(f"reference builder {dataset_name!r} is already registered")
    _REFERENCE_BUILDERS[dataset_name] = builder
    return builder


def _discover_reference_plugins() -> None:
    """Import every additive reference builder exactly once."""

    global _REFERENCE_PLUGINS_DISCOVERED
    if _REFERENCE_PLUGINS_DISCOVERED:
        return
    with _REFERENCE_DISCOVERY_LOCK:
        if _REFERENCE_PLUGINS_DISCOVERED:
            return
        from . import reference_plugins

        for module in pkgutil.iter_modules(reference_plugins.__path__):
            if module.name.startswith("_"):
                continue
            importlib.import_module(f"{reference_plugins.__name__}.{module.name}")
        _REFERENCE_PLUGINS_DISCOVERED = True


@dataclass(frozen=True)
class ReferenceGold:
    """Independent gold files and landable reference datasets."""

    files: Mapping[str, Any]
    data_files: Mapping[str, Any] = field(default_factory=dict)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _cents(value: str) -> int:
    amount = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(amount * 100)


def _money(cents: int, divisor: int = 1) -> str:
    """Format cents, rounding only when a diagnostic average is requested."""

    value = Decimal(cents) / Decimal(divisor) / Decimal("100")
    if divisor != 1:
        value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(value, ".2f")


def _grain_trap_gold(data_dir: Path) -> ReferenceGold:
    """Compute exact-cent revenue and diagnostic averages with SQL.

    The graded value is an order-grain sum of already-cent-quantized amounts.
    The averages remain useful diagnostics, but their display rounding is not
    allowed to determine whether a consumer's answer is correct.
    """

    orders = _read_csv(data_dir / "orders.csv")
    line_items = _read_csv(data_dir / "line_items.csv")
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            """
            CREATE TABLE orders (
                order_id TEXT NOT NULL,
                region TEXT NOT NULL,
                order_amount_cents INTEGER NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE line_items (
                line_item_id TEXT NOT NULL,
                order_id TEXT NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?)",
            [
                (row["order_id"], row["region"], _cents(row["order_amount"]), row["status"])
                for row in orders
            ],
        )
        connection.executemany(
            "INSERT INTO line_items VALUES (?, ?)",
            [(row["line_item_id"], row["order_id"]) for row in line_items],
        )

        # Correct: one amount contributes once per active order.
        correct_rows = connection.execute(
            """
            SELECT region, SUM(order_amount_cents), COUNT(*)
            FROM orders
            WHERE status <> 'deleted'
            GROUP BY region
            ORDER BY region
            """
        ).fetchall()
        # Known-wrong control: the same amount is repeated once per joined
        # line item.  The exact inner join intentionally drops true orphans.
        naive_rows = connection.execute(
            """
            SELECT o.region, SUM(o.order_amount_cents), COUNT(li.line_item_id)
            FROM orders AS o
            INNER JOIN line_items AS li ON li.order_id = o.order_id
            WHERE o.status <> 'deleted'
            GROUP BY o.region
            ORDER BY o.region
            """
        ).fetchall()
        control_total = connection.execute(
            """
            SELECT COALESCE(SUM(order_amount_cents), 0)
            FROM orders
            WHERE status <> 'deleted'
            """
        ).fetchone()[0]
    finally:
        connection.close()

    naive_by_region = {row[0]: (row[1], row[2]) for row in naive_rows}
    region_diagnostics: list[dict[str, Any]] = []
    for region, total_cents, order_count in correct_rows:
        naive_total, joined_count = naive_by_region[region]
        region_diagnostics.append(
            {
                "region": region,
                "regional_revenue": float(_money(total_cents)),
                "naive_fanout_revenue": float(_money(naive_total)),
                "correct_typical_order_value": float(_money(total_cents, order_count)),
                "naive_fanout_order_value": float(_money(naive_total, joined_count)),
                "active_order_count": order_count,
                "joined_line_item_count": joined_count,
            }
        )
    answer_rows = [
        {
            "region": row["region"],
            "regional_revenue": row["regional_revenue"],
        }
        for row in region_diagnostics
    ]
    control_total_value = float(_money(control_total))
    return ReferenceGold(
        files={
            "grain_trap_by_region.json": answer_rows,
            "grain_trap_control.json": [{"control_total": control_total_value}],
            "grain_trap_diagnostics.json": {
                "dataset": "grain_trap",
                "regions": region_diagnostics,
                "control_total": control_total_value,
                "active_order_count": sum(
                    row["active_order_count"] for row in region_diagnostics
                ),
                "filters": {
                    "orders": "status <> 'deleted'",
                    "line_items": "exact inner join on order_id; orphan keys excluded",
                },
            },
        },
        data_files={
            "grain_trap_control.json": [{"control_total": control_total_value}],
        },
    )


def _zero_row_optional_gold(data_dir: Path) -> ReferenceGold:
    """Count required and optional resources using SQL, including exact zero."""

    primary = _read_csv(data_dir / "primary.csv")
    optional = _read_csv(data_dir / "optional_events.csv")
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE primary_resource (record_id TEXT)")
        connection.execute("CREATE TABLE optional_resource (event_id TEXT)")
        connection.executemany(
            "INSERT INTO primary_resource VALUES (?)",
            [(row["record_id"],) for row in primary],
        )
        connection.executemany(
            "INSERT INTO optional_resource VALUES (?)",
            [(row["event_id"],) for row in optional],
        )
        required_count = connection.execute(
            "SELECT COUNT(*) FROM primary_resource"
        ).fetchone()[0]
        optional_count = connection.execute(
            "SELECT COUNT(*) FROM optional_resource"
        ).fetchone()[0]
    finally:
        connection.close()
    return ReferenceGold(
        files={
            "zero_row_optional_counts.json": [
                {"resource": "optional_events", "row_count": optional_count},
                {"resource": "primary", "row_count": required_count},
            ],
            "zero_row_optional_diagnostics.json": [
                {
                    "resource": "optional_events",
                    "row_count": optional_count,
                    "required": False,
                },
                {"resource": "primary", "row_count": required_count, "required": True},
            ],
        }
    )


def _call_reference_builder(
    builder: ReferenceBuilder, data_path: Path, source_path: Path
) -> ReferenceGold:
    """Call legacy builders unchanged and pass the optional hidden source dir when accepted."""

    try:
        parameters = inspect.signature(builder).parameters
    except (TypeError, ValueError):
        parameters = {}
    source_parameter = parameters.get("source_dir")
    accepts_keywords = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    if source_parameter is not None and source_parameter.kind is not inspect.Parameter.POSITIONAL_ONLY:
        return builder(data_path, source_dir=source_path)
    if accepts_keywords:
        return builder(data_path, source_dir=source_path)
    return builder(data_path)


def read_source_table(source_dir: str | Path, name: str) -> list[dict[str, Any]]:
    """Read one generated JSON source table for an independent reference builder."""

    path = Path(source_dir) / f"{name}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read source table {name!r}: {exc}") from exc
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"source table {name!r} must contain a JSON array of objects")
    return value


def reference_gold(
    dataset_name: str,
    data_dir: str | Path,
    *,
    source_dir: str | Path | None = None,
) -> ReferenceGold:
    """Return frozen gold content for ``dataset_name`` from source files."""

    _discover_reference_plugins()
    data_path = Path(data_dir)
    resolved_source_dir = Path(source_dir) if source_dir is not None else data_path.parent / "source"
    try:
        builder = _REFERENCE_BUILDERS[dataset_name]
    except KeyError as exc:
        available = ", ".join(sorted(_REFERENCE_BUILDERS))
        raise ValueError(f"unknown dataset {dataset_name!r}; choose one of: {available}") from exc
    return _call_reference_builder(builder, data_path, resolved_source_dir)


register_reference_builder("grain_trap", _grain_trap_gold)
register_reference_builder("zero_row_optional", _zero_row_optional_gold)


def _write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError("gold CSV row-set cannot be empty")
    columns = tuple(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="raise",
            lineterminator="\n",
            quoting=csv.QUOTE_MINIMAL,
            quotechar='"',
            doublequote=True,
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in columns})


def write_reference_gold(
    dataset_name: str,
    data_dir: str | Path,
    gold_dir: str | Path,
    *,
    reference: ReferenceGold | None = None,
    source_dir: str | Path | None = None,
) -> ReferenceGold:
    """Calculate and write gold files with pinned text serialization."""

    result = reference or reference_gold(dataset_name, data_dir, source_dir=source_dir)
    destination = Path(gold_dir)
    destination.mkdir(parents=True, exist_ok=True)
    for filename, content in result.files.items():
        path = destination / filename
        if filename.endswith(".csv"):
            _write_csv(path, content)
        elif filename.endswith(".json"):
            path.write_text(
                json.dumps(content, ensure_ascii=True, sort_keys=True, indent=2)
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        else:
            raise ValueError(f"unsupported gold extension: {filename}")
    return result


def write_reference_data(
    dataset_name: str,
    data_dir: str | Path,
    *,
    reference: ReferenceGold | None = None,
    source_dir: str | Path | None = None,
) -> ReferenceGold:
    """Write independent reference datasets that closures may land and query."""

    result = reference or reference_gold(dataset_name, data_dir, source_dir=source_dir)
    destination = Path(data_dir)
    for filename, content in result.data_files.items():
        path = destination / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if filename.endswith(".json"):
            path.write_text(
                json.dumps(content, ensure_ascii=True, sort_keys=True, indent=2)
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        elif filename.endswith(".csv"):
            _write_csv(path, content)
        else:
            raise ValueError(f"unsupported reference data extension: {filename}")
    return result


compute_gold = reference_gold
generate_gold = write_reference_gold


__all__ = [
    "ReferenceGold",
    "compute_gold",
    "generate_gold",
    "reference_gold",
    "register_reference_builder",
    "read_source_table",
    "write_reference_data",
    "write_reference_gold",
]
