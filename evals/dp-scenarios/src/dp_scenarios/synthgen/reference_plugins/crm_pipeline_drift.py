"""Independent redacted gold from generated CRM source JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..reference import ReferenceGold, read_source_table, register_reference_builder


def _crm_pipeline_drift_gold(data_dir: Path, *, source_dir: Path) -> ReferenceGold:
    del data_dir
    files: dict[str, Any] = {}
    for version, amount_field in (("v1", "amount"), ("v2", "deal_value")):
        rows = read_source_table(source_dir, f"deals_{version}")
        files[f"crm_pipeline_drift_{version}.json"] = {
            "rows": [
                {
                    "deal_id": row["id"],
                    "stage": row["stage"],
                    "amount": row[amount_field],
                    "updated_at": row["updatedAt"],
                }
                for row in rows
                if row["status"] == "active"
            ]
        }
    return ReferenceGold(files=files)


register_reference_builder("crm_pipeline_drift", _crm_pipeline_drift_gold)
