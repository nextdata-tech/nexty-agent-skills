"""Independent reference model for the finance close scenario."""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from ..reference import ReferenceGold, register_reference_builder


def _amount(raw: str) -> tuple[Decimal, bool]:
    value = raw.strip().replace(",", "")
    parenthesized = value.startswith("(") and value.endswith(")")
    if parenthesized:
        value = "-" + value[1:-1]
    return Decimal(value), parenthesized


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def _finance_close_gold(data_dir: Path) -> ReferenceGold:
    rows = list(csv.DictReader((data_dir / "close_entries.csv").open(encoding="utf-8", newline="")))
    reconciled: list[dict[str, str]] = []
    missing_fx = 0
    weekend_closes = 0
    negative_amounts = 0
    parenthesized_amounts = 0
    for row in rows:
        amount, parenthesized = _amount(row["amount"])
        negative_amounts += amount < 0
        parenthesized_amounts += parenthesized
        close_day = date.fromisoformat(row["close_date"])
        weekend_closes += close_day.weekday() >= 5
        raw_fx = row["fx_rate"].strip()
        if not raw_fx:
            missing_fx += 1
            continue
        converted = amount * Decimal(raw_fx)
        reconciled.append(
            {
                "close_id": row["close_id"],
                "account_id": row["account_id"],
                "currency": row["currency"],
                "amount_eur": _money(converted),
            }
        )
    total = sum((Decimal(row["amount_eur"]) for row in reconciled), Decimal("0"))
    reconciliation: dict[str, Any] = {
        "rows": reconciled,
        "total_eur": _money(total),
        "excluded_missing_fx": missing_fx,
    }
    diagnostics = {
        "input_row_count": len(rows),
        "converted_row_count": len(reconciled),
        "missing_fx_count": missing_fx,
        "weekend_close_count": weekend_closes,
        "negative_amount_count": int(negative_amounts),
        "parenthesized_amount_count": int(parenthesized_amounts),
    }
    return ReferenceGold(
        files={
            "finance_close_reconciliation.json": reconciliation,
            "finance_close_diagnostics.json": diagnostics,
        },
        data_files={"finance_close_reference.json": reconciliation},
    )


register_reference_builder("finance_close", _finance_close_gold)

