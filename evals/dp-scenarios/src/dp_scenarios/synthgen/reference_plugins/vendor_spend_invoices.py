"""Independent vendor/category spend oracle for the B9 invoice fixture.

Reads only the emitted CSV bytes. Recognizes two kinds of amount evidence in
``invoice_text``: a labelled numeric total (``EUR 1,234.56``) or a stated
number-word span (``twelve thousand four hundred fifty``). Never imports the
dataset builder's constants, and never infers an amount from the AP control
total -- the AP rows are read and checked independently, purely as a
consistency cross-check.
"""

from __future__ import annotations

import csv
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..reference import ReferenceGold, register_reference_builder


_NUMERIC_PATTERN = re.compile(r"EUR\s+([0-9][0-9,]*\.[0-9]{2})")

_ONES = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
_TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000}
_NUMBER_WORDS = frozenset(_ONES) | frozenset(_TEENS) | frozenset(_TENS) | frozenset(_SCALES) | {"and"}

_WORD_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
    + r")(?:[ \t-]+(?:"
    + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
    + r"))*\b",
    re.IGNORECASE,
)


def _words_to_int(phrase: str) -> int:
    total = 0
    current = 0
    for raw_token in re.split(r"[\s-]+", phrase.strip()):
        token = raw_token.lower()
        if token == "and":
            continue
        if token in _ONES:
            current += _ONES[token]
        elif token in _TEENS:
            current += _TEENS[token]
        elif token in _TENS:
            current += _TENS[token]
        elif token == "hundred":
            current = (current or 1) * 100
        elif token == "thousand":
            total += (current or 1) * 1000
            current = 0
        else:
            raise ValueError(f"unrecognized number word: {token!r}")
    return total + current


def _extract_amount(invoice_text: str) -> tuple[int | None, str | None]:
    """Return ``(amount_cents, amount_phrase)`` or ``(None, None)`` if absent.

    A labelled numeric total takes priority over a word span; the fixture
    never states both for one invoice. Only a genuine match counts -- no
    residual, guess, or zero default is ever produced here.
    """

    numeric = _NUMERIC_PATTERN.search(invoice_text)
    if numeric is not None:
        phrase = numeric.group(0)
        cents = int(Decimal(numeric.group(1).replace(",", "")) * 100)
        return cents, phrase

    best: tuple[int, int, str] | None = None  # (start, end, phrase)
    for match in _WORD_PATTERN.finditer(invoice_text):
        span_words = match.group(0).split()
        # A lone connector or a single small cardinal (e.g. a date ordinal
        # remnant) is not amount evidence; require at least a ten/hundred/
        # thousand scale word or two or more words to count as a phrase.
        if len(span_words) < 2:
            continue
        if not any(word.lower() in _SCALES or word.lower() in _TEENS or word.lower() in _TENS for word in span_words):
            continue
        if best is None or (match.end() - match.start()) > (best[1] - best[0]):
            best = (match.start(), match.end(), match.group(0))
    if best is None:
        return None, None
    _, _, phrase = best
    try:
        value = _words_to_int(phrase)
    except ValueError:
        return None, None
    return value * 100, phrase


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _vendor_spend_invoices_gold(data_dir: Path) -> ReferenceGold:
    vendors = _read_rows(data_dir / "vendors.csv")
    invoices = _read_rows(data_dir / "invoices.csv")
    ap_totals = _read_rows(data_dir / "ap_vendor_totals.csv")

    vendor_category = {row["vendor_id"]: row["category"] for row in vendors}
    vendor_name = {row["vendor_id"]: row["vendor_name"] for row in vendors}

    invoice_rows: list[dict[str, Any]] = []
    vendor_amounts: dict[str, int] = {vendor["vendor_id"]: 0 for vendor in vendors}
    for row in invoices:
        invoice_id = row["invoice_id"]
        vendor_id = row["vendor_id"]
        text = row["invoice_text"]
        amount_cents, amount_phrase = _extract_amount(text)
        stated = amount_cents is not None
        if stated:
            vendor_amounts[vendor_id] += amount_cents
        invoice_rows.append(
            {
                "invoice_id": invoice_id,
                "vendor_id": vendor_id,
                "category": vendor_category[vendor_id],
                "amount_stated": stated,
                "amount_cents": amount_cents,
                "amount_phrase": amount_phrase,
            }
        )
    invoice_rows.sort(key=lambda item: item["invoice_id"])

    ap_control_cents = {row["vendor_id"]: int(Decimal(row["ap_total_eur"]) * 100) for row in ap_totals}
    if set(ap_control_cents) != set(vendor_amounts):
        raise ValueError("AP control vendor set does not match the vendor roster")

    vendor_rows: list[dict[str, Any]] = []
    for vendor_id in sorted(vendor_amounts):
        computed = vendor_amounts[vendor_id]
        control = ap_control_cents[vendor_id]
        if computed != control:
            raise ValueError(
                f"vendor {vendor_id!r} extracted spend {computed} does not "
                f"reconcile with the AP control total {control}"
            )
        vendor_rows.append(
            {
                "vendor_id": vendor_id,
                "vendor_name": vendor_name[vendor_id],
                "category": vendor_category[vendor_id],
                "amount_cents": computed,
                "ap_total_cents": control,
            }
        )

    # The scoreable "answer" row-set is the agent-facing spend shape: no
    # AP-control column, since that total is a cross-check input, not part of
    # the requested vendor/category spend output.
    answer_rows = [
        {
            "vendor_id": row["vendor_id"],
            "vendor_name": row["vendor_name"],
            "category": row["category"],
            "amount_cents": row["amount_cents"],
        }
        for row in vendor_rows
    ]

    category_amounts: dict[str, int] = {}
    for row in vendor_rows:
        category_amounts[row["category"]] = category_amounts.get(row["category"], 0) + row["amount_cents"]
    category_rows = [
        {"category": category, "amount_cents": amount}
        for category, amount in sorted(category_amounts.items())
    ]

    grand_total_cents = sum(category_amounts.values())
    priced = [row for row in invoice_rows if row["amount_stated"]]
    unpriced = [row for row in invoice_rows if not row["amount_stated"]]

    diagnostics = {
        "invoice_count": len(invoice_rows),
        "priced_invoice_count": len(priced),
        "unpriced_invoice_count": len(unpriced),
        "unpriced_invoice_ids": [row["invoice_id"] for row in unpriced],
        "word_phrase_invoice_ids": sorted(
            row["invoice_id"] for row in invoice_rows if row["amount_stated"] and not row["amount_phrase"].startswith("EUR")
        ),
        "vendor_count": len(vendor_rows),
        "category_count": len(category_rows),
        "grand_total_cents": grand_total_cents,
        "vendor_ap_totals_cents": {row["vendor_id"]: row["ap_total_cents"] for row in vendor_rows},
    }
    return ReferenceGold(
        files={
            "vendor_spend_invoices_answer.json": answer_rows,
            "vendor_spend_invoices_category.json": category_rows,
            "vendor_spend_invoices_invoices.json": invoice_rows,
            "vendor_spend_invoices_diagnostics.json": diagnostics,
        }
    )


register_reference_builder("vendor_spend_invoices", _vendor_spend_invoices_gold)
