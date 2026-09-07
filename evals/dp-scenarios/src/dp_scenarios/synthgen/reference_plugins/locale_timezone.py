"""Independent gold for the C6 locale and timezone-boundary drill."""

from __future__ import annotations

import csv
from collections import Counter
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..reference import ReferenceGold, register_reference_builder


def _locale_timezone_gold(data_dir: Path) -> ReferenceGold:
    with (data_dir / "events.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    timezones = {row["source_timezone"] for row in rows}
    if timezones != {"America/New_York"}:
        raise ValueError("source timezone is missing or inconsistent")
    source_timezone = next(iter(timezones))
    source_zone = ZoneInfo(source_timezone)

    local_days: Counter[str] = Counter()
    utc_days: Counter[str] = Counter()
    local_amounts: dict[str, Decimal] = {}
    utc_amounts: dict[str, Decimal] = {}
    local_total = Decimal("0")
    utc_total = Decimal("0")
    for row in rows:
        amount = Decimal(row["amount"])
        local_timestamp = datetime.fromisoformat(row["source_local_timestamp"])
        recorded_utc = datetime.fromisoformat(row["event_utc"])
        if local_timestamp.tzinfo is None or recorded_utc.tzinfo is None:
            raise ValueError("timestamps must include offsets")
        localized = local_timestamp.replace(tzinfo=None).replace(tzinfo=source_zone)
        derived_utc = localized.astimezone(timezone.utc)
        if local_timestamp.utcoffset() != localized.utcoffset() or derived_utc != recorded_utc:
            raise ValueError("event_utc does not match the source-local timestamp")
        local_day = localized.date().isoformat()
        utc_day = derived_utc.date().isoformat()
        local_days[local_day] += 1
        utc_days[utc_day] += 1
        local_amounts[local_day] = local_amounts.get(local_day, Decimal("0")) + amount
        utc_amounts[utc_day] = utc_amounts.get(utc_day, Decimal("0")) + amount
        local_total += amount
        utc_total += amount
    shifted = sum(
        1
        for row in rows
        if row["source_local_timestamp"][:10] != row["event_utc"][:10]
    )
    local_daily = [
        {
            "day": day,
            "row_count": local_days[day],
            "total_amount": format(local_amounts[day], ".2f"),
        }
        for day in sorted(local_days)
    ]
    utc_daily = [
        {
            "day": day,
            "row_count": utc_days[day],
            "total_amount": format(utc_amounts[day], ".2f"),
        }
        for day in sorted(utc_days)
    ]
    result: dict[str, Any] = {
        "source_timezone": source_timezone,
        "row_count": len(rows),
        "boundary_shift_rows": shifted,
        "boundary_shift_fraction": round(shifted / len(rows), 8),
        "source_local_total": format(local_total, ".2f"),
        "utc_total": format(utc_total, ".2f"),
        "unicode_category": "契約",
        "local_daily": local_daily,
        "utc_daily": utc_daily,
    }
    query_category = "契約"
    query_row_count = sum(row["category"] == query_category for row in rows)
    if query_row_count == 0:
        raise ValueError(f"query category is absent: {query_category}")
    diagnostics = {
        "local_day_count": len(local_daily),
        "utc_day_count": len(utc_daily),
        "totals_invariant": local_total == utc_total,
        "query_category": query_category,
        "query_row_count": query_row_count,
    }
    return ReferenceGold(
        files={
            "locale_timezone_reconciliation.json": result,
            "locale_timezone_diagnostics.json": diagnostics,
        }
    )


register_reference_builder("locale_timezone", _locale_timezone_gold)
