"""Minimal fixture identity for the route-backed CRM pipeline scenario."""

from __future__ import annotations

import random
from typing import Mapping

from ..datasets import BASE_INSTANT, DatasetDefinition
from ..defects import Frame
from ..registry import register_dataset


def _build_crm_pipeline(seed: int, rng: random.Random) -> Mapping[str, Frame]:
    del rng
    return {
        "deals": [
            {
                "deal_id": f"FIXTURE-{seed}-001",
                "stage": "qualification",
                "amount": 1,
                "updated_at": "2024-01-01T00:00:00+00:00",
            }
        ]
    }


register_dataset(
    DatasetDefinition(
        name="crm_pipeline",
        base_instant=BASE_INSTANT,
        table_columns={"deals": ("deal_id", "stage", "amount", "updated_at")},
        injectors=(),
        builder=_build_crm_pipeline,
        description="Route-backed CRM fixture identity; the graded rows come from the mock source.",
        plant="crm_pipeline_pagination",
        requires_explicit_plant=True,
    )
)

