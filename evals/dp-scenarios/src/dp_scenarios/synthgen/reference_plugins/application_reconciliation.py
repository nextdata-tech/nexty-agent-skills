"""Independent gold for the C2 application-count dispute."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ..reference import ReferenceGold, register_reference_builder


def _application_reconciliation_gold(data_dir: Path) -> ReferenceGold:
    with (data_dir / "applications.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with (data_dir / "dashboard_snapshot.csv").open(encoding="utf-8", newline="") as handle:
        snapshot = next(csv.DictReader(handle))

    export_count = len(rows)
    # The two exclusions are deliberately disjoint: status filtering removes
    # every non-active row, while tombstone filtering removes only active
    # tombstones. This makes double-counting observable in the fixture.
    status_excluded = sum(row["status"] != "active" for row in rows)
    tombstones = sum(
        row["status"] == "active" and row["tombstoned"] == "true" for row in rows
    )
    dashboard_count = sum(row["status"] == "active" and row["tombstoned"] == "false" for row in rows)
    declared_dashboard = int(snapshot["value"])
    if declared_dashboard != dashboard_count:
        raise ValueError("dashboard snapshot disagrees with the filtered source")

    dispute: dict[str, Any] = {
        "export_count": export_count,
        "dashboard_active_count": dashboard_count,
        "difference": export_count - dashboard_count,
        "status_filter_exclusions": status_excluded,
        "tombstone_exclusions": tombstones,
    }
    lineage = {
        "source_table": "applications",
        "dashboard_table": "dashboard_snapshot",
        "clauses": [
            {
                "id": "active_status",
                "predicate": "status != active",
                "excludes": status_excluded,
            },
            {
                "id": "tombstone_filter",
                "predicate": "status = active AND tombstoned = true",
                "excludes": tombstones,
            },
        ],
        "disjoint_exclusion_total": status_excluded + tombstones,
    }
    answer = [dict(dispute)]
    return ReferenceGold(
        files={
            "application_reconciliation_answer.json": answer,
            "application_reconciliation_dispute.json": dispute,
            "application_reconciliation_lineage.json": lineage,
        }
    )


register_reference_builder("application_reconciliation", _application_reconciliation_gold)
