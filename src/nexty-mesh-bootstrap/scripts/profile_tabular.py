#!/usr/bin/env python3
"""Profile local tabular samples for mesh bootstrap discovery.

The script is intentionally read-only: it prints a JSON profile to stdout and
does not write files.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


MAX_ROWS = 1000
MAX_SAMPLE_VALUES = 5


def infer_scalar(value: Any) -> str:
    if value is None or value == "":
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    text = str(value)
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return "boolean"
    try:
        int(text)
        return "integer"
    except (TypeError, ValueError):
        pass
    try:
        float(text)
        return "number"
    except (TypeError, ValueError):
        pass
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return "date_or_timestamp"
    return "string"


def merge_types(types: Counter[str]) -> str:
    non_null = [name for name in types if name != "null"]
    if not non_null:
        return "string"
    if len(non_null) == 1:
        return non_null[0]
    if set(non_null) <= {"integer", "number"}:
        return "number"
    return "string"


def profile_rows(path: Path, rows: list[dict[str, Any]], total_rows: int | None) -> dict[str, Any]:
    columns: dict[str, dict[str, Any]] = {}
    field_names: list[str] = []
    for row in rows:
        for key in row:
            if key not in field_names:
                field_names.append(key)

    for name in field_names:
        values = [row.get(name) for row in rows]
        types = Counter(infer_scalar(value) for value in values)
        samples: list[Any] = []
        for value in values:
            if value in (None, "") or value in samples:
                continue
            samples.append(value)
            if len(samples) >= MAX_SAMPLE_VALUES:
                break
        columns[name] = {
            "inferred_type": merge_types(types),
            "nullable": types.get("null", 0) > 0,
            "observed_types": dict(types),
            "sample_values": samples,
        }

    partition_hints = [
        name
        for name in field_names
        if name.lower() in {"date", "dt", "day", "month", "year", "timestamp", "created_at", "updated_at"}
        or name.lower().endswith(("_date", "_dt", "_at"))
    ]

    return {
        "path": str(path),
        "format": path.suffix.lower().lstrip(".") or "unknown",
        "rows_profiled": len(rows),
        "total_rows": total_rows,
        "columns": columns,
        "partition_or_freshness_hints": partition_hints,
    }


def read_csv(path: Path) -> tuple[list[dict[str, Any]], int | None]:
    rows: list[dict[str, Any]] = []
    total = 0
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            total += 1
            if len(rows) < MAX_ROWS:
                rows.append(dict(row))
    return rows, total


def read_json(path: Path) -> tuple[list[dict[str, Any]], int | None]:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                data = value
                break
    if isinstance(data, dict):
        return [data], 1
    if not isinstance(data, list):
        raise ValueError("JSON root must be an object or array of objects")
    rows = [row for row in data[:MAX_ROWS] if isinstance(row, dict)]
    return rows, len(data)


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], int | None]:
    rows: list[dict[str, Any]] = []
    total = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            total += 1
            if len(rows) < MAX_ROWS:
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
    return rows, total


def read_parquet(path: Path) -> tuple[list[dict[str, Any]], int | None]:
    try:
        import pandas as pd  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Parquet profiling requires pandas and a parquet engine such as pyarrow") from exc

    frame = pd.read_parquet(path)
    total = len(frame)
    rows = frame.head(MAX_ROWS).where(frame.notna(), None).to_dict(orient="records")
    return rows, total


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: profile_tabular.py <csv|json|jsonl|parquet-path>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1]).expanduser().resolve()
    if not path.exists():
        print(f"not found: {path}", file=sys.stderr)
        return 2

    suffix = path.suffix.lower()
    if suffix == ".csv":
        rows, total = read_csv(path)
    elif suffix == ".json":
        rows, total = read_json(path)
    elif suffix in {".jsonl", ".ndjson"}:
        rows, total = read_jsonl(path)
    elif suffix == ".parquet":
        rows, total = read_parquet(path)
    else:
        print(f"unsupported file type: {suffix}", file=sys.stderr)
        return 2

    print(json.dumps(profile_rows(path, rows, total), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
