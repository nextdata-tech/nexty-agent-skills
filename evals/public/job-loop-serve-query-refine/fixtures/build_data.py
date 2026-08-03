#!/usr/bin/env python3
"""Build and validate the deterministic desktop Loop CSV fixture.

The CSVs are committed so an eval never needs to generate them.  Running this
file is still useful: it proves the foreign keys, grains, and the deliberately
different aggregate fingerprints that make dropped filters observable.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "data"


def read(name: str) -> list[dict[str, str]]:
    with (ROOT / name / f"{name}.csv").open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def total(rows: list[dict[str, str]]) -> float:
    return round(sum(float(row["amount_eur"]) for row in rows), 2)


def rows_for_filter(rows: list[dict[str, str]], label: str, spain: set[str]) -> list[dict[str, str]]:
    q2 = lambda row: "2025-04-01" <= row["order_date"] < "2025-07-01"
    if label == "all":
        return rows
    if label == "q2":
        return [row for row in rows if q2(row)]
    if label == "spain":
        return [row for row in rows if row["customer_id"] in spain]
    if label == "spain_q2":
        return [row for row in rows if row["customer_id"] in spain and q2(row)]
    raise AssertionError(f"unknown filter: {label}")


def aggregate(rows: list[dict[str, str]], metric: str) -> float:
    if metric == "sum_amount":
        return total(rows)
    if metric == "avg_amount":
        return round(total(rows) / len(rows), 2) if rows else 0.0
    if metric == "count_orders":
        return float(len(rows))
    if metric == "sum_overdue":
        return float(sum(row["is_overdue"].lower() == "true" for row in rows))
    raise AssertionError(f"unknown metric: {metric}")


def selection_signature(rows: list[dict[str, str]], metric: str, group: str | None,
                        customer_fields: dict[str, dict[str, str]], ordered_top3: bool = False) -> tuple[tuple[str, float], ...]:
    buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = "__scalar__" if group is None else (
            customer_fields[row["customer_id"]][group] if group in {"billing_country", "segment", "customer_name"}
            else row[group]
        )
        buckets[key].append(row)
    values = [(key, aggregate(bucket, metric)) for key, bucket in buckets.items()]
    if ordered_top3:
        return tuple(sorted(values, key=lambda value: (-value[1], value[0]))[:3])
    return tuple(sorted(values))


def main() -> None:
    customers = read("customers")
    orders = read("orders")
    customer_ids = [r["customer_id"] for r in customers]
    order_ids = [r["order_id"] for r in orders]
    assert len(customer_ids) == len(set(customer_ids)), "customers grain is not unique"
    assert len(order_ids) == len(set(order_ids)), "orders grain is not unique"
    assert {r["customer_id"] for r in orders} <= set(customer_ids), "orphan FK"

    q2 = [r for r in orders if "2025-04-01" <= r["order_date"] < "2025-07-01"]
    spain = {r["customer_id"] for r in customers if r["billing_country"] == "Spain"}
    fingerprints = {
        "Spain in Q2": total([r for r in q2 if r["customer_id"] in spain]),
        "all countries in Q2": total(q2),
        "Spain all time": total([r for r in orders if r["customer_id"] in spain]),
        "all countries all time": total(orders),
    }
    assert len(set(fingerprints.values())) == len(fingerprints), fingerprints
    assert fingerprints["Spain in Q2"] == 330.0, fingerprints

    customer_fields = {r["customer_id"]: r for r in customers}
    segments = {r["customer_id"]: r["segment"] for r in customers}
    by_segment: dict[str, float] = defaultdict(float)
    for row in q2:
        by_segment[segments[row["customer_id"]]] += float(row["amount_eur"])
    assert sorted(round(v, 2) for v in by_segment.values()) == [420.0, 510.0, 1440.0]

    overdue: dict[str, int] = defaultdict(int)
    for row in orders:
        overdue[row["product_category"]] += row["is_overdue"].lower() == "true"
    assert dict(overdue) == {"Software": 4, "Services": 1, "Hardware": 2}

    # Compute (rather than hardcode) every correct answer signature and compare
    # it with every alternate (column x aggregation x grouping x filter)
    # selection the checker could mistake for it. This is the fixture's
    # collision-freedom contract: regeneration can never silently turn a wrong
    # governed selection into a passing answer through coincidental data.
    target_selections = {
        "spain_q2_total": ("spain_q2", "sum_amount", None, False),
        "q2_amount_by_segment": ("q2", "sum_amount", "segment", False),
        "overdue_by_category": ("all", "sum_overdue", "product_category", False),
        "top_customers_by_amount": ("all", "sum_amount", "customer_name", True),
        "average_by_segment_q2": ("q2", "avg_amount", "segment", False),
    }
    filters = ("all", "q2", "spain", "spain_q2")
    metrics = ("sum_amount", "avg_amount", "count_orders", "sum_overdue")
    groups = (None, "billing_country", "segment", "product_category", "customer_name")
    for target, target_selection in target_selections.items():
        target_signature = selection_signature(
            rows_for_filter(orders, target_selection[0], spain), target_selection[1],
            target_selection[2], customer_fields, target_selection[3],
        )
        assert target_signature, f"{target} unexpectedly has no rows"
        order_modes = (False, True) if target == "top_customers_by_amount" else (False,)
        for filter_name in filters:
            for metric in metrics:
                for group in groups:
                    for ordered_top3 in order_modes:
                        candidate = (filter_name, metric, group, ordered_top3)
                        if candidate == target_selection:
                            continue
                        candidate_signature = selection_signature(
                            rows_for_filter(orders, filter_name, spain), metric, group,
                            customer_fields, ordered_top3,
                        )
                        assert candidate_signature != target_signature, (
                            f"{target} collides with wrong selection {candidate}: {target_signature}"
                        )
    print("fixture OK: unique grains, contained FK, and computed collision-free aggregate signatures")


if __name__ == "__main__":
    main()
