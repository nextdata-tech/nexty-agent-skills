"""Independent monthly headcount and attrition oracle for B6."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ..reference import ReferenceGold, register_reference_builder


SUPPRESSION_THRESHOLD = 5
_REPORT_MONTHS = ("2024-01", "2024-02", "2024-03")


def _headcount_attrition_gold(data_dir: Path) -> ReferenceGold:
    with (data_dir / "hr_export.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    by_month_department: dict[str, dict[str, set[str]]] = {}
    for row in rows:
        month = row["snapshot_month"]
        department = row["department"]
        token = row["opaque_person_token"]
        by_month_department.setdefault(month, {}).setdefault(department, set()).add(token)

    departments = sorted({row["department"] for row in rows})
    report_rows: list[dict[str, Any]] = []
    for month in _REPORT_MONTHS:
        year, month_number = (int(part) for part in month.split("-"))
        previous_month = f"{year - 1:04d}-12" if month_number == 1 else f"{year:04d}-{month_number - 1:02d}"
        for department in departments:
            current = by_month_department[month].get(department, set())
            previous = by_month_department[previous_month].get(department, set())
            headcount = len(current)
            joiners = len(current - previous)
            leavers = len(previous - current)
            suppressed = headcount < SUPPRESSION_THRESHOLD
            report_rows.append(
                {
                    "month": month,
                    "department": department,
                    "headcount": None if suppressed else headcount,
                    "joiners": None if suppressed else joiners,
                    "leavers": None if suppressed else leavers,
                    "attrition_rate_bps": (
                        None
                        if suppressed
                        else (leavers * 10_000 * 2 + len(previous)) // (2 * len(previous))
                    ),
                    "suppressed": suppressed,
                }
            )

    report_rows.sort(key=lambda item: (item["month"], item["department"]))
    diagnostics = {
        "snapshot_row_count": len(rows),
        "report_months": list(_REPORT_MONTHS),
        "department_count": len(departments),
        "suppressed_department_month_count": sum(row["suppressed"] for row in report_rows),
        "suppression_threshold": SUPPRESSION_THRESHOLD,
    }
    output = {
        "dataset": "headcount_attrition",
        "seed": 29,
        "threshold": SUPPRESSION_THRESHOLD,
        "rows": report_rows,
        "diagnostics": diagnostics,
    }
    return ReferenceGold(files={"headcount_attrition.json": output})


register_reference_builder("headcount_attrition", _headcount_attrition_gold)
