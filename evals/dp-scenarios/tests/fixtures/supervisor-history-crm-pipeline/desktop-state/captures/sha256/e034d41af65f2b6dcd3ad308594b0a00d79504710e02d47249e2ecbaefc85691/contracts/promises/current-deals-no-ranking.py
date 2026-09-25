"""Output promise: no row or field on the landed `deals` relation
represents a priority or attention ranking.

Independent witness: checked against the physical table's own column
catalog (`PRAGMA table_info`), not against transform logic -- proving no
ranking/score column was ever materialized rather than restating that the
transform chose not to compute one.
"""

from __future__ import annotations

import duckdb

from nxd import data_product
from nxd.core.context import DuckDbOutput, VerifyResult, VerifyResultEnum

_FORBIDDEN_SUBSTRINGS = ("priority", "rank", "attention", "score")


@data_product.on_verify()
def verify(output: DuckDbOutput) -> VerifyResult:
    table = output.full_table_name("deals")
    with duckdb.connect(output.path, read_only=True) as conn:
        columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]

    offending = [
        column
        for column in columns
        if any(term in column.lower() for term in _FORBIDDEN_SUBSTRINGS)
    ]

    if offending:
        return VerifyResult(
            VerifyResultEnum.FAILED,
            {
                "contract": "current-deals-no-ranking",
                "model": "deals",
                "guarantee": (
                    "No row or field in this output represents a priority "
                    "or attention ranking."
                ),
                "observed_offending_columns": offending,
                "expected_offending_columns": [],
                "all_columns": columns,
            },
        )
    return VerifyResult(
        VerifyResultEnum.PASS,
        {
            "contract": "current-deals-no-ranking",
            "model": "deals",
            "observed_offending_columns": [],
            "all_columns": columns,
        },
    )


if __name__ == "__main__":
    data_product.verify()
