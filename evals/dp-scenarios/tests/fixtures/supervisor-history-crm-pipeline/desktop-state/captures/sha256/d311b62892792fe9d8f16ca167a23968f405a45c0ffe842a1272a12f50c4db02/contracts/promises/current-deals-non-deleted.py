"""Output promise: every landed deal row is current (non-deleted).

Independent witness: `deals.status` is landed as an internal-only column
specifically so this verifier can check it directly against the physical
table, rather than re-deriving the ingestion filter's own result. A deal
is current only when status is a known, present value other than the
deleted tombstone; a deleted status and a missing/empty/"unknown" status
are both excluded at ingestion, so no landed row should ever carry one of
those values here. A row that does means a deleted or unrecognized-status
deal slipped through the filter.
"""

from __future__ import annotations

import duckdb

from nxd import data_product
from nxd.core.context import DuckDbOutput, VerifyResult, VerifyResultEnum


@data_product.on_verify()
def verify(output: DuckDbOutput) -> VerifyResult:
    table = output.full_table_name("deals")
    with duckdb.connect(output.path, read_only=True) as conn:
        offending = conn.execute(
            f"SELECT deal_id, status FROM {table} "
            f"WHERE status = 'deleted' OR status = 'unknown' "
            f"OR status IS NULL OR status = ''"
        ).fetchall()

    if offending:
        return VerifyResult(
            VerifyResultEnum.FAILED,
            {
                "contract": "current-deals-non-deleted",
                "model": "deals",
                "guarantee": "Every output row is a current (non-deleted) deal.",
                "observed_offending_rows": len(offending),
                "expected_offending_rows": 0,
                "examples": repr(offending[:3]),
            },
        )
    return VerifyResult(
        VerifyResultEnum.PASS,
        {
            "contract": "current-deals-non-deleted",
            "model": "deals",
            "observed_offending_rows": 0,
        },
    )


if __name__ == "__main__":
    data_product.verify()
