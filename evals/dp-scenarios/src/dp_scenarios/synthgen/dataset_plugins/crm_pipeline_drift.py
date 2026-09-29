"""Runner-private v1/v2 CRM deal sources for the B11 drift scenario."""

from __future__ import annotations

import random
from typing import Mapping

from ..datasets import BASE_INSTANT, DatasetDefinition
from ..defects import Frame, _sentinel_for
from ..registry import register_dataset


def _build_crm_pipeline_drift(seed: int, rng: random.Random) -> Mapping[str, Frame]:
    del rng
    owner_marker = _sentinel_for("owner.email", seed=seed, dataset="crm_pipeline_drift")
    champion_marker = _sentinel_for(
        "champion.email", seed=seed, dataset="crm_pipeline_drift"
    )
    v1: Frame = [
        {
            "id": "DEAL-2001",
            "name": "Northwind Renewal",
            "stage": "negotiation",
            "amount": 48200,
            "status": "active",
            "updatedAt": "2024-01-05T10:00:00+00:00",
            "owner": {"name": "Analyst One", "email": owner_marker},
        },
        {
            "id": "DEAL-2002",
            "name": "Acme Expansion",
            "stage": "qualification",
            "amount": 15600,
            "status": "active",
            "updatedAt": "2024-01-04T16:30:00+00:00",
            "owner": {"name": "Analyst Two", "email": "analyst-two@example.invalid"},
        },
        {
            "id": "DEAL-2003",
            "name": "Globex Renewal",
            "stage": "closed_won",
            "amount": 72300,
            "status": "active",
            "updatedAt": "2024-01-06T09:15:00+00:00",
            "owner": {"name": "Analyst One", "email": owner_marker},
        },
        {
            "id": "DEAL-2004",
            "name": "Initech Upsell",
            "stage": "prospecting",
            "amount": 9100,
            "status": "active",
            "updatedAt": "2024-01-02T11:45:00+00:00",
            "owner": {
                "name": "Analyst Three",
                "email": "analyst-three@example.invalid",
            },
        },
        {
            "id": "DEAL-2005",
            "name": "Umbrella Renewal",
            "stage": "closed_lost",
            "amount": 26400,
            "status": "active",
            "updatedAt": "2024-01-03T14:20:00+00:00",
            "owner": {"name": "Analyst Two", "email": "analyst-two@example.invalid"},
        },
        {
            "id": "DEAL-2006",
            "name": "Deleted Renewal",
            "stage": "closed_lost",
            "amount": 3000,
            "updatedAt": "2024-01-01T09:00:00+00:00",
            "status": "deleted",
            "owner": {"name": "Analyst Four", "email": "analyst-four@example.invalid"},
        },
    ]
    v2: Frame = [
        {"deal_value" if key == "amount" else key: value for key, value in row.items()}
        for row in v1
    ]
    v2[1]["stage"] = "verbal_commit"
    v2[1]["champion"] = {"name": "Synthetic Champion Two", "email": champion_marker}
    v2.append(
        {
            "id": "DEAL-2007",
            "name": "New Provisional Deal",
            "stage": "verbal_commit",
            "deal_value": 31850,
            "status": "active",
            "updatedAt": "2024-01-08T12:00:00+00:00",
            "owner": {"name": "Analyst Two", "email": "analyst-two@example.invalid"},
            "champion": {"name": "Synthetic Champion Seven", "email": champion_marker},
        }
    )
    return {"deals_v1": v1, "deals_v2": v2}


register_dataset(
    DatasetDefinition(
        name="crm_pipeline_drift",
        base_instant=BASE_INSTANT,
        table_columns={},
        source_tables=("deals_v1", "deals_v2"),
        injectors=(),
        builder=_build_crm_pipeline_drift,
        description="Stateful CRM source with an initially hidden schema and stage drift.",
        plant="crm_pipeline_drift",
        requires_explicit_plant=True,
    )
)
