"""Source fixture for the C2 wrong-number reconciliation scenario."""

from __future__ import annotations

import random
from typing import Mapping

from ..datasets import BASE_INSTANT, DatasetDefinition
from ..defects import Frame
from ..registry import register_dataset


def _build_application_reconciliation(seed: int, rng: random.Random) -> Mapping[str, Frame]:
    del rng
    applications: Frame = []
    for index in range(353):
        applications.append(
            {
                "application_id": f"APP-{seed}-{index + 1:03d}",
                "status": "active",
                "tombstoned": "false",
                "submitted_date": "2024-04-01",
                "amount": "100.00",
            }
        )
    for index in range(22):
        applications.append(
            {
                "application_id": f"APP-{seed}-{354 + index:03d}",
                "status": "withdrawn",
                "tombstoned": "false",
                "submitted_date": "2024-04-01",
                "amount": "100.00",
            }
        )
    for index in range(8):
        applications.append(
            {
                "application_id": f"APP-{seed}-{376 + index:03d}",
                "status": "withdrawn",
                "tombstoned": "true",
                "submitted_date": "2024-04-01",
                "amount": "100.00",
            }
        )
    for index in range(8):
        applications.append(
            {
                "application_id": f"APP-{seed}-{384 + index:03d}",
                "status": "active",
                "tombstoned": "true",
                "submitted_date": "2024-04-01",
                "amount": "100.00",
            }
        )
    return {
        "applications": applications,
        "dashboard_snapshot": [
            {
                "snapshot_date": "2024-04-30",
                "metric": "active_applications",
                "value": "353",
            }
        ],
    }


register_dataset(
    DatasetDefinition(
        name="application_reconciliation",
        base_instant=BASE_INSTANT,
        table_columns={
            "applications": (
                "application_id",
                "status",
                "tombstoned",
                "submitted_date",
                "amount",
            ),
            "dashboard_snapshot": ("snapshot_date", "metric", "value"),
        },
        injectors=(),
        builder=_build_application_reconciliation,
        description=(
            "An application export and a dashboard snapshot expose status and "
            "tombstone fields for a disjoint lineage-reconciliation exercise."
        ),
        plant="application_reconciliation_dispute",
        requires_explicit_plant=True,
    )
)
