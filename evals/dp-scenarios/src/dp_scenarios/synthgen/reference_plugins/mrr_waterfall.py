"""Independent CSV reference model for the B7 MRR waterfall fixture."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..reference import ReferenceGold, register_reference_builder

_MOVEMENTS = ("new", "expansion", "contraction", "churn", "reactivation")


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _month(value: str) -> str:
    if len(value) < 7:
        raise ValueError(f"timestamp is too short to contain a month: {value!r}")
    return value[:7]


def _deduplicate_events(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep one exact event copy and reject conflicting event identities."""

    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        event_id = row.get("event_id", "")
        if not event_id:
            raise ValueError("subscription event is missing event_id")
        previous = by_id.get(event_id)
        if previous is not None and previous != row:
            raise ValueError(f"conflicting duplicate subscription event {event_id!r}")
        by_id[event_id] = row
    return sorted(by_id.values(), key=lambda row: (row["effective_at"], row["event_id"]))


def _evaluate(
    events: list[dict[str, str]],
    *,
    month_column: str = "effective_at",
    gross_directions: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Compute customer closes, net-classified bridge, and monthly controls."""

    customers = sorted({row["customer_id"] for row in events})
    months = sorted({_month(row[month_column]) for row in events})
    by_month_customer: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in events:
        by_month_customer[_month(row[month_column])][row["customer_id"]].append(row)

    balances = dict.fromkeys(customers, 0)
    had_positive_before: set[str] = set()
    customer_month_rows: list[dict[str, Any]] = []
    waterfall_rows: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []

    for month in months:
        month_opening = sum(balances.values())
        month_movements = dict.fromkeys(_MOVEMENTS, 0)
        for customer_id in customers:
            opening = balances[customer_id]
            customer_events = by_month_customer[month].get(customer_id, [])
            deltas = [int(row["mrr_delta_cents"]) for row in customer_events]
            closing = opening + sum(deltas)
            if closing < 0:
                raise ValueError(
                    f"customer {customer_id!r} has negative closing MRR in {month}"
                )

            movement: str | None = None
            amount = 0
            if opening == 0 and closing > 0:
                movement = "reactivation" if customer_id in had_positive_before else "new"
                amount = closing
            elif opening > 0 and closing == 0:
                movement = "churn"
                amount = opening
            elif opening > 0 and closing > 0:
                if gross_directions:
                    expansion = sum(delta for delta in deltas if delta > 0)
                    contraction = -sum(delta for delta in deltas if delta < 0)
                    month_movements["expansion"] += expansion
                    month_movements["contraction"] += contraction
                elif closing > opening:
                    movement = "expansion"
                    amount = closing - opening
                elif closing < opening:
                    movement = "contraction"
                    amount = opening - closing

            if movement is not None and amount:
                month_movements[movement] += amount
            customer_month_rows.append(
                {
                    "customer_id": customer_id,
                    "month": month,
                    "opening_mrr_cents": opening,
                    "closing_mrr_cents": closing,
                    "net_change_cents": closing - opening,
                    "had_positive_before_month": customer_id in had_positive_before,
                }
            )
            balances[customer_id] = closing
            if closing > 0:
                had_positive_before.add(customer_id)

        for movement in _MOVEMENTS:
            amount = month_movements[movement]
            if amount:
                waterfall_rows.append(
                    {"month": month, "movement": movement, "amount_cents": amount}
                )
        controls.append(
            {
                "month": month,
                "opening_mrr_cents": month_opening,
                "new_cents": month_movements["new"],
                "expansion_cents": month_movements["expansion"],
                "contraction_cents": month_movements["contraction"],
                "churn_cents": month_movements["churn"],
                "reactivation_cents": month_movements["reactivation"],
                "closing_mrr_cents": sum(balances.values()),
            }
        )

    return customer_month_rows, waterfall_rows, controls


def _mrr_waterfall_gold(data_dir: Path) -> ReferenceGold:
    physical_events = _read_rows(data_dir / "subscription_events.csv")
    contacts = _read_rows(data_dir / "customer_contacts.csv")
    events = _deduplicate_events(physical_events)
    customer_month_rows, answer, controls = _evaluate(events)
    _, gross_answer, _ = _evaluate(events, gross_directions=True)
    _, no_dedup_answer, _ = _evaluate(physical_events)
    _, received_month_answer, _ = _evaluate(events, month_column="received_at")

    diagnostics = {
        "source_row_counts": {
            "subscription_events_physical": len(physical_events),
            "subscription_event_ids": len({row["event_id"] for row in physical_events}),
            "customer_contacts": len(contacts),
        },
        "expected_model_row_counts": {
            "billing_events_dedup": len(events),
            "customer_month_mrr": len(customer_month_rows),
            "mrr_waterfall": len(answer),
        },
        "variant_row_counts": {
            "gross": len(gross_answer),
            "no_dedup": len(no_dedup_answer),
            "received_month": len(received_month_answer),
        },
    }
    return ReferenceGold(
        files={
            "mrr_waterfall_answer.json": answer,
            "customer_month_mrr.json": customer_month_rows,
            "mrr_waterfall_controls.json": controls,
            "mrr_waterfall_diagnostics.json": diagnostics,
            "mrr_waterfall_gross.json": gross_answer,
            "mrr_waterfall_no_dedup.json": no_dedup_answer,
            "mrr_waterfall_received_month.json": received_month_answer,
        }
    )


register_reference_builder("mrr_waterfall", _mrr_waterfall_gold)
