"""Transform for pharma-rx-demo (DP_RX).

Seeds the ROWS of the promised `dispenses` model's managed table. The table
STRUCTURE and the single-table `DISPENSES_SEMANTIC` view are created earlier by
the `@on_provision` hook (provision.py), which runs in Phase A before this
transform. This transform only writes the data the output-port promise verifies.

The `.transform()` is also what bundles the sibling `registry.py` / `tools.py` /
`provision.py` modules into the image (the `**/*.py` glob runs on the
transform/compute path).
"""

import pandas as pd
from nxd.data_product.context import Snowflake


def transform(snowflake: Snowflake) -> None:
    from snowflake import connector
    from snowflake.connector.pandas_tools import write_pandas

    if snowflake is None or not snowflake.schema:
        print("PHARMA_RX_DIAG transform skipped — no Snowflake schema in context")
        return

    dispenses = pd.DataFrame(
        [
            {
                "DISPENSE_ID": 1,
                "SUBJECT_ID": 1,
                "PRODUCT_ID": 1,
                "UNITS": 30,
                "DISPENSE_CHANNEL": "retail",
                "PRESCRIBER_NPI": "1234567890",
            },
            {
                "DISPENSE_ID": 2,
                "SUBJECT_ID": 1,
                "PRODUCT_ID": 2,
                "UNITS": 60,
                "DISPENSE_CHANNEL": "mail-order",
                "PRESCRIBER_NPI": "1234567890",
            },
            {
                "DISPENSE_ID": 3,
                "SUBJECT_ID": 2,
                "PRODUCT_ID": 1,
                "UNITS": 30,
                "DISPENSE_CHANNEL": "retail",
                "PRESCRIBER_NPI": "9876543210",
            },
            {
                "DISPENSE_ID": 4,
                "SUBJECT_ID": 3,
                "PRODUCT_ID": 3,
                "UNITS": 90,
                "DISPENSE_CHANNEL": "specialty",
                "PRESCRIBER_NPI": "5556667770",
            },
            {
                "DISPENSE_ID": 5,
                "SUBJECT_ID": 3,
                "PRODUCT_ID": 3,
                "UNITS": 45,
                "DISPENSE_CHANNEL": "mail-order",
                "PRESCRIBER_NPI": "5556667770",
            },
        ]
    )

    conn = connector.connect(
        user=snowflake.user,
        account=snowflake.account,
        warehouse=snowflake.warehouse,
        role=snowflake.role,
        database=snowflake.database,
        schema=snowflake.schema,
        ocsp_fail_open=True,
        **snowflake.connector_params(),
    )
    try:
        # Seed the PROMISED `dispenses` model's managed table. Truncate-and-load
        # so repeated runs stay deterministic (the provision hook created the
        # table with CREATE TABLE IF NOT EXISTS, so it may already hold rows from
        # a prior run).
        managed = snowflake.full_table_name("dispenses")
        cur = conn.cursor()
        try:
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
        finally:
            cur.close()
        write_pandas(
            conn,
            dispenses,
            managed.split(".")[-1].strip('"'),
            database=snowflake.database,
            schema=snowflake.schema,
        )
        print(f"PHARMA_RX_DIAG seeded {managed} rows={len(dispenses)}")
    finally:
        conn.close()
