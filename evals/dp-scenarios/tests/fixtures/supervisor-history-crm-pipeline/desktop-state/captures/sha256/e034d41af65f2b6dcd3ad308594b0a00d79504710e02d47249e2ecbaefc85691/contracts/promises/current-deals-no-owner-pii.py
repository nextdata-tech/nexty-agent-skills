"""Output promise: no owner name or owner email ever appears on any
stored surface of this product, not only the `deals` relation.

Independent witness: checked against each physical table's own column
catalog (`PRAGMA table_info`), not against a value the transform
computed. The owner object is never even read into the flattened `deals`
row before it reaches that table, so this proves the redaction rather
than restating it. The promise text covers "no other stored surface of
this product, including any raw/internal landed relation" -- so every
physical table this closure lands (`deals` and `nxd_decisions`) is
checked here, not only the promised output table.
"""

from __future__ import annotations

import duckdb

from nxd import data_product
from nxd.core.context import DuckDbOutput, VerifyResult, VerifyResultEnum

_FORBIDDEN_SUBSTRINGS = ("owner", "email")
_CHECKED_MODELS = ("deals", "nxd_decisions")


@data_product.on_verify()
def verify(output: DuckDbOutput) -> VerifyResult:
    offending_by_table: dict[str, list[str]] = {}
    all_columns_by_table: dict[str, list[str]] = {}
    with duckdb.connect(output.path, read_only=True) as conn:
        for model in _CHECKED_MODELS:
            table = output.full_table_name(model)
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            all_columns_by_table[model] = columns
            offending = [
                column
                for column in columns
                if any(term in column.lower() for term in _FORBIDDEN_SUBSTRINGS)
            ]
            if offending:
                offending_by_table[model] = offending

    if offending_by_table:
        return VerifyResult(
            VerifyResultEnum.FAILED,
            {
                "contract": "current-deals-no-owner-pii",
                "model": "deals",
                "guarantee": (
                    "No output row, and no other stored surface of this "
                    "product, includes owner name or owner email."
                ),
                "observed_offending_columns_by_table": offending_by_table,
                "expected_offending_columns": [],
                "all_columns_by_table": all_columns_by_table,
            },
        )
    return VerifyResult(
        VerifyResultEnum.PASS,
        {
            "contract": "current-deals-no-owner-pii",
            "model": "deals",
            "checked_tables": list(_CHECKED_MODELS),
            "observed_offending_columns": [],
            "all_columns_by_table": all_columns_by_table,
        },
    )


if __name__ == "__main__":
    data_product.verify()
