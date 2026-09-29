"""Output promise pipeline-stage-in-enum on the deals model.

Every stage value is one of prospecting, qualification, negotiation, closed_won
or closed_lost. The check reads the landed table only.
"""

import duckdb as duckdb_lib

from nxd import data_product
from nxd.core.context import DuckDbOutput, VerifyResult, VerifyResultEnum

CONTRACT = "pipeline-stage-in-enum"
MODEL = "deals"
STAGES = ("prospecting", "qualification", "negotiation", "closed_won", "closed_lost")


@data_product.on_verify()
def verify(duckdb: DuckDbOutput) -> VerifyResult:
    table = duckdb.full_table_name(MODEL)
    connection = duckdb_lib.connect(duckdb.path, read_only=True)
    try:
        rows = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        placeholders = ", ".join("?" for _ in STAGES)
        offending = connection.execute(
            f"SELECT stage, count(*) FROM {table} "
            f"WHERE stage IS NULL OR stage NOT IN ({placeholders}) "
            f"GROUP BY stage ORDER BY stage",
            list(STAGES),
        ).fetchall()
    finally:
        connection.close()
    if offending:
        return VerifyResult(
            VerifyResultEnum.FAILED,
            {
                "contract": CONTRACT,
                "model": MODEL,
                "guarantee": "every stage is one of " + ", ".join(STAGES),
                "observed_rows": rows,
                "observed_offending_stages": repr(offending[:5]),
                "expected_offending_rows": 0,
            },
        )
    return VerifyResult(
        VerifyResultEnum.PASS,
        {
            "contract": CONTRACT,
            "model": MODEL,
            "observed_rows": rows,
            "observed_offending_rows": 0,
        },
    )


if __name__ == "__main__":
    data_product.verify()
