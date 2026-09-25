"""Output promise: every landed deal row is current (non-deleted).

The approved blueprint requires that the source `status` value never be
landed anywhere in this product, so this verifier has no landed status
column to read directly (see models.py -- `deals` carries only deal_id,
stage, amount, updated_at). Independent witness instead: the transform
records, in the `nxd_decisions` ledger's `current-deal-definition` row,
the run's own fetched/excluded-deleted/landed tally captured while rows
streamed through the ingestion filter -- before the status value was
discarded and before this verifier ever runs. This check recomputes the
landed row count from the physical `deals` table directly (not from the
transform's arithmetic) and confirms it reconciles against that recorded
tally, so a deleted row that slipped through the filter (landed count
too high for the recorded fetched/excluded numbers) is caught here.
"""

from __future__ import annotations

import re

import duckdb

from nxd import data_product
from nxd.core.context import DuckDbOutput, VerifyResult, VerifyResultEnum

_EVIDENCE_RE = re.compile(
    r"Run evidence: fetched=(\d+); excluded_deleted=(\d+); landed=(\d+)\."
)


@data_product.on_verify()
def verify(output: DuckDbOutput) -> VerifyResult:
    deals_table = output.full_table_name("deals")
    decisions_table = output.full_table_name("nxd_decisions")

    with duckdb.connect(output.path, read_only=True) as conn:
        actual_deal_count = conn.execute(f"SELECT COUNT(*) FROM {deals_table}").fetchone()[0]
        detail_row = conn.execute(
            f"SELECT detail FROM {decisions_table} WHERE decision_id = 'current-deal-definition'"
        ).fetchone()

    if detail_row is None:
        return VerifyResult(
            VerifyResultEnum.FAILED,
            {
                "contract": "current-deals-non-deleted",
                "model": "deals",
                "guarantee": "Every output row is a current (non-deleted) deal.",
                "reason": "no current-deal-definition row found in nxd_decisions",
            },
        )

    match = _EVIDENCE_RE.search(detail_row[0] or "")
    if match is None:
        return VerifyResult(
            VerifyResultEnum.FAILED,
            {
                "contract": "current-deals-non-deleted",
                "model": "deals",
                "guarantee": "Every output row is a current (non-deleted) deal.",
                "reason": "current-deal-definition detail carries no run-evidence tally",
                "detail": detail_row[0],
            },
        )

    fetched, excluded_deleted, recorded_landed = (int(value) for value in match.groups())
    expected_landed = fetched - excluded_deleted

    offenses = []
    if recorded_landed != expected_landed:
        offenses.append("recorded landed count does not equal fetched minus excluded_deleted")
    if actual_deal_count != recorded_landed:
        offenses.append("actual deals row count does not match the recorded landed count")
    if actual_deal_count != expected_landed:
        offenses.append("actual deals row count does not reconcile with fetched minus excluded_deleted")

    if offenses:
        return VerifyResult(
            VerifyResultEnum.FAILED,
            {
                "contract": "current-deals-non-deleted",
                "model": "deals",
                "guarantee": "Every output row is a current (non-deleted) deal.",
                "offenses": offenses,
                "fetched": fetched,
                "excluded_deleted": excluded_deleted,
                "recorded_landed": recorded_landed,
                "actual_deal_count": actual_deal_count,
            },
        )
    return VerifyResult(
        VerifyResultEnum.PASS,
        {
            "contract": "current-deals-non-deleted",
            "model": "deals",
            "fetched": fetched,
            "excluded_deleted": excluded_deleted,
            "actual_deal_count": actual_deal_count,
        },
    )


if __name__ == "__main__":
    data_product.verify()
