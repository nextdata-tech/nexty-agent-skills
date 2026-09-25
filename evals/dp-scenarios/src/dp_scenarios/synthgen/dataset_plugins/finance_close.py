"""Deterministic month-end close inputs for the finance reconciliation scenario."""

from __future__ import annotations

from decimal import Decimal
import random
from typing import Mapping

from ..datasets import BASE_INSTANT, DatasetDefinition, InjectorSpec
from ..defects import Frame
from ..registry import register_dataset


def _build_finance_close(seed: int, rng: random.Random) -> Mapping[str, Frame]:
    """Build fixed close rows with hostile amount and FX representations."""

    del rng
    rows: Frame = [
        {
            "close_id": f"CLOSE-{seed}-001",
            "account_id": "ACCT-001",
            "close_date": "2024-01-31",
            "currency": "EUR",
            "amount": Decimal("1234.50"),
            "fx_rate": Decimal("1.00"),
            "status": "posted",
            "notes": "standard euro close",
        },
        {
            "close_id": f"CLOSE-{seed}-002",
            "account_id": "ACCT-002",
            "close_date": "2024-01-30",
            "currency": "USD",
            "amount": "1,250.00",
            "fx_rate": Decimal("0.92"),
            "status": "posted",
            "notes": "comma-formatted amount",
        },
        {
            "close_id": f"CLOSE-{seed}-003",
            "account_id": "ACCT-003",
            "close_date": "2024-01-29",
            "currency": "GBP",
            "amount": "(200.00)",
            "fx_rate": Decimal("1.17"),
            "status": "posted",
            "notes": "parenthesized credit",
        },
        {
            "close_id": f"CLOSE-{seed}-004",
            "account_id": "ACCT-004",
            "close_date": "2024-01-28",
            "currency": "USD",
            "amount": Decimal("300.00"),
            "fx_rate": Decimal("0.92"),
            "status": "posted",
            "notes": "standard dollar close",
        },
        {
            "close_id": f"CLOSE-{seed}-005",
            "account_id": "ACCT-005",
            "close_date": "2024-01-27",
            "currency": "JPY",
            "amount": Decimal("15000.00"),
            # Keep the four-decimal FX rate as text: the generic fixture
            # serializer intentionally formats Decimal cells to cents.
            "fx_rate": "0.0062",
            "status": "posted",
            "notes": "small-unit currency",
        },
        {
            "close_id": f"CLOSE-{seed}-006",
            "account_id": "ACCT-006",
            "close_date": "2024-01-06",
            "currency": "USD",
            "amount": "(250.00)",
            "fx_rate": "",
            "status": "posted",
            "notes": "weekend rate unavailable",
        },
        {
            "close_id": f"CLOSE-{seed}-007",
            "account_id": "ACCT-007",
            "close_date": "2024-01-26",
            "currency": "EUR",
            "amount": Decimal("85.00"),
            "fx_rate": Decimal("1.00"),
            "status": "posted",
            "notes": "small euro close",
        },
    ]
    ap_vendor_contacts: Frame = [
        {"vendor_id": "VENDOR-001", "contact_email": "ap-contact-001@example.invalid"},
        {"vendor_id": "VENDOR-002", "contact_email": "ap-contact-002@example.invalid"},
    ]
    return {"close_entries": rows, "ap_vendor_contacts": ap_vendor_contacts}


register_dataset(
    DatasetDefinition(
        name="finance_close",
        base_instant=BASE_INSTANT,
        table_columns={
            "close_entries": (
                "close_id",
                "account_id",
                "close_date",
                "currency",
                "amount",
                "fx_rate",
                "status",
                "notes",
            ),
            "ap_vendor_contacts": ("vendor_id", "contact_email"),
        },
        injectors=(
            InjectorSpec("ap_vendor_contacts", "pii_sentinels", {"columns": ["contact_email"]}),
        ),
        builder=_build_finance_close,
        description=(
            "Month-end close entries use comma-formatted and parenthesized amounts. "
            "One weekend USD entry has no FX rate and must be excluded with a warning."
        ),
        plant="finance_close_reconciliation",
        requires_explicit_plant=True,
    )
)
