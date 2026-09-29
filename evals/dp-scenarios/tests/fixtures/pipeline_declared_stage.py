"""Output promise pipeline-declared-stage: every row has one declared stage."""

import duckdb

from nxd import data_product
from nxd.core.context import DuckDbOutput, VerifyResult, VerifyResultEnum

DECLARED_STAGES = ("prospecting", "qualification", "negotiation", "closed_won", "closed_lost")


@data_product.on_verify()
def verify(output: DuckDbOutput) -> VerifyResult:
    table = output.full_table_name("pipeline")
    placeholders = ", ".join("?" for _ in DECLARED_STAGES)
    connection = duckdb.connect(output.path, read_only=True)
    try:
        offending = connection.execute(
            f"SELECT stage, COUNT(*) FROM {table} "
            f"WHERE stage IS NULL OR stage NOT IN ({placeholders}) GROUP BY stage",
            list(DECLARED_STAGES),
        ).fetchall()
        total = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        connection.close()
    if total == 0 or offending:
        return VerifyResult(
            VerifyResultEnum.FAILED,
            {
                "contract": "pipeline-declared-stage",
                "model": "pipeline",
                "guarantee": "Every output row has one of the declared stages.",
                "observed_offending_stages": repr(offending[:5]),
                "expected_offending_stages": 0,
                "observed_rows": total,
                "expected_min_rows": 1,
            },
        )
    return VerifyResult(
        VerifyResultEnum.PASS,
        {
            "contract": "pipeline-declared-stage",
            "model": "pipeline",
            "observed_offending_stages": 0,
            "observed_rows": total,
        },
    )


if __name__ == "__main__":
    data_product.verify()
