"""Deterministic subscription events for the B7 MRR waterfall fixture."""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Mapping

from ..datasets import BASE_INSTANT, DatasetDefinition, InjectorSpec
from ..defects import Frame
from ..registry import register_dataset


_EVENTS: tuple[tuple[str, str, str, int, int], ...] = (
    ("E01", "C001", "2024-01", 2, 10_000),
    ("E02", "C002", "2024-01", 8, 20_000),
    ("E03", "C003", "2024-01", 14, 15_000),
    ("E04", "C006", "2024-01", 20, 7_000),
    ("E05", "C001", "2024-02", 2, 2_000),
    ("E06", "C002", "2024-02", 7, -5_000),
    ("E07", "C003", "2024-02", 13, -4_000),
    ("E08", "C003", "2024-02", 20, 6_000),
    ("E09", "C004", "2024-02", 25, 8_000),
    ("E10", "C006", "2024-02", 28, -7_000),
    ("E11", "C001", "2024-03", 3, -12_000),
    ("E12", "C002", "2024-03", 8, 3_000),
    ("E13", "C003", "2024-03", 13, 1_000),
    ("E14", "C004", "2024-03", 18, -2_000),
    ("E15", "C005", "2024-03", 28, 5_000),
    ("E16", "C006", "2024-03", 30, 9_000),
    ("E17", "C001", "2024-04", 3, 12_000),
    ("E18", "C002", "2024-04", 9, -18_000),
    ("E19", "C003", "2024-04", 15, -3_000),
    ("E20", "C004", "2024-04", 21, 2_000),
    ("E21", "C005", "2024-04", 27, 5_000),
)

_LATE_ARRIVALS = {
    "E08": "2024-03-17T00:00:00+00:00",
    "E15": "2024-04-18T00:00:00+00:00",
    "E16": "2024-04-19T00:00:00+00:00",
}


def _build_mrr_waterfall(seed: int, rng: random.Random) -> Mapping[str, Frame]:
    """Build an effective-dated event stream and one out-of-scope export."""

    del seed, rng
    rows: list[dict[str, object]] = []
    for event_id, customer_id, month, day, delta in _EVENTS:
        effective_date = date.fromisoformat(f"{month}-{day:02d}")
        effective_at = f"{effective_date.isoformat()}T00:00:00+00:00"
        received_at = _LATE_ARRIVALS.get(
            event_id,
            f"{(effective_date + timedelta(days=1)).isoformat()}T00:00:00+00:00",
        )
        rows.append(
            {
                "event_id": event_id,
                "customer_id": customer_id,
                "effective_at": effective_at,
                "received_at": received_at,
                "mrr_delta_cents": delta,
            }
        )
    # Two physical duplicates are deliberate. Their fields match the original
    # event exactly; the independent reference rejects any conflicting copy.
    by_id = {str(row["event_id"]): row for row in rows}
    rows.extend(dict(by_id[event_id]) for event_id in ("E08", "E16"))
    rows.sort(key=lambda row: (str(row["received_at"]), str(row["event_id"])))

    contacts: Frame = [
        {"customer_id": "C003", "billing_email": "billing-c003@example.invalid"},
        {"customer_id": "C001", "billing_email": "billing-c001@example.invalid"},
        {"customer_id": "C002", "billing_email": "billing-c002@example.invalid"},
        {"customer_id": "C004", "billing_email": "billing-c004@example.invalid"},
        {"customer_id": "C005", "billing_email": "billing-c005@example.invalid"},
        {"customer_id": "C006", "billing_email": "billing-c006@example.invalid"},
    ]
    return {"subscription_events": rows, "customer_contacts": contacts}


register_dataset(
    DatasetDefinition(
        name="mrr_waterfall",
        base_instant=BASE_INSTANT,
        table_columns={
            "subscription_events": (
                "event_id",
                "customer_id",
                "effective_at",
                "received_at",
                "mrr_delta_cents",
            ),
            "customer_contacts": ("customer_id", "billing_email"),
        },
        injectors=(
            InjectorSpec("customer_contacts", "pii_sentinels", {"columns": ["billing_email"]}),
        ),
        builder=_build_mrr_waterfall,
        description="Customer subscription records span four monthly reporting periods.",
        plant="B7-same-month",
        requires_explicit_plant=True,
    )
)
