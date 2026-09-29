"""Independent gold for the B8 product-usage fixture, from the hidden JSON.

Deliberately does not import ``dataset_plugins.product_usage``: it re-derives
every count from the raw v1/v2/v3 event rows with its own grouping code, so a
bug in the fixture builder's own aggregation cannot also corrupt the gold
that is supposed to catch it.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..reference import ReferenceGold, read_source_table, register_reference_builder

_FEATURES = ("search", "dashboard", "export")


def _week_start(occurred_at: str) -> str:
    day = datetime.fromisoformat(occurred_at.replace("Z", "+00:00")).date()
    monday = day.fromordinal(day.toordinal() - day.weekday())
    return monday.isoformat()


def _deduplicate_union(
    v1_events: list[dict[str, Any]], v2_events: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Union v1 and v2 by ``event_id``, rejecting a conflicting duplicate.

    This is the only correct incremental read of a rolling-window source: a
    naive high watermark on ``occurred_at`` would miss the late arrivals, and
    replacing the whole landed set with v2's served window would silently
    drop the accounts only v1 ever served (2024-04-08).
    """

    union: dict[str, dict[str, Any]] = {}
    for row in v1_events:
        union[row["event_id"]] = row
    for row in v2_events:
        event_id = row["event_id"]
        previous = union.get(event_id)
        if previous is not None and previous != row:
            raise ValueError(f"conflicting duplicate usage event {event_id!r}")
        union[event_id] = row
    return union


def _weekly_active_accounts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_week: dict[str, set[str]] = {}
    for row in events:
        by_week.setdefault(_week_start(row["occurred_at"]), set()).add(row["account_id"])
    return [
        {"week_start": week, "active_accounts": len(accounts)}
        for week, accounts in sorted(by_week.items())
    ]


def _weekly_feature_adoption(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_week_feature: dict[tuple[str, str], set[str]] = {}
    for row in events:
        key = (_week_start(row["occurred_at"]), row["feature"])
        by_week_feature.setdefault(key, set()).add(row["account_id"])
    rows = [
        {"week_start": week, "feature": feature, "active_accounts": len(accounts)}
        for (week, feature), accounts in by_week_feature.items()
    ]
    return sorted(rows, key=lambda row: (row["week_start"], row["feature"]))


def _event_date(row: dict[str, Any]) -> date:
    return datetime.fromisoformat(row["occurred_at"].replace("Z", "+00:00")).date()


def _late_event_ids(v1_events: list[dict[str, Any]], v2_events: list[dict[str, Any]]) -> list[str]:
    """Return only genuinely late arrivals: new ids dated within v1's already-served window.

    A v2-only id dated 2024-04-22 is simply the newest ordinary day, which v1
    never claimed to have served. A v2-only id dated on or before v1's last
    served day (2024-04-21) is a late arrival: v1 already reported that day
    complete, and v2 revises that report.
    """

    v1_ids = {row["event_id"] for row in v1_events}
    last_served_day = max(_event_date(row) for row in v1_events)
    return sorted(
        row["event_id"]
        for row in v2_events
        if row["event_id"] not in v1_ids and _event_date(row) <= last_served_day
    )


def _product_usage_gold(data_dir: Path, *, source_dir: Path) -> ReferenceGold:
    del data_dir
    v1_events = read_source_table(source_dir, "usage_events_v1")
    v2_events = read_source_table(source_dir, "usage_events_v2")
    v3_events = read_source_table(source_dir, "usage_events_v3")
    status_v1 = read_source_table(source_dir, "usage_export_status_v1")
    status_v2 = read_source_table(source_dir, "usage_export_status_v2")

    union = _deduplicate_union(v1_events, v2_events)
    landed_events = list(union.values())
    answer = _weekly_active_accounts(landed_events)
    feature_adoption = _weekly_feature_adoption(landed_events)
    late_ids = _late_event_ids(v1_events, v2_events)
    earliest_late = min(row["occurred_at"] for row in v2_events if row["event_id"] in set(late_ids))

    diagnostics = {
        "source_row_counts": {
            "v1": len(v1_events),
            "v2": len(v2_events),
            "v3": len(v3_events),
        },
        "expected_model_row_counts": {
            "usage_events": len(union),
            "weekly_active_accounts": len(answer),
            "weekly_feature_adoption": len(feature_adoption),
            "usage_export_status": 1,
        },
        "late_event_ids": late_ids,
        "earliest_late_timestamp": earliest_late,
    }
    controls = [
        {"state": "v1", **status_v1[0]},
        {"state": "v2", **status_v2[0]},
    ]
    return ReferenceGold(
        files={
            "product_usage_answer.json": answer,
            "product_usage_feature_adoption.json": feature_adoption,
            "product_usage_controls.json": controls,
            "product_usage_diagnostics.json": diagnostics,
        }
    )


register_reference_builder("product_usage", _product_usage_gold)
