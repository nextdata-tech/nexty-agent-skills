"""Transform for pharma-rx-demo (DP_RX) — self-seeded.

Two jobs, all in this DP's OWN Snowflake schema:

1.  Seed the base ``dispenses`` table the semantic MCP tools read. Self-contained:
    no dependency on any other DP's schema or pre-existing data. CREATE OR REPLACE
    so re-runs are idempotent.
2.  Write a one-row marker table (``dispenses_smoke_marker``) — the promised
    output model — so the storage port's produce-verification passes.

The semantic-view provisioning from the old registry.py / provision.py
implementation is removed. The auto-generated ``run_semantic_query`` (from the
``.semantic_tools()`` flag) compiles governed SQL against the base table
directly, reading the kernel-delivered ``<root>/.nxd/semantic/<model>.json``
payloads. No pre-provisioned view is required.
"""

from nxd.data_product.context import Snowflake


def transform(snowflake: Snowflake) -> None:
    import pandas as pd
    from snowflake.connector.pandas_tools import write_pandas

    from snowflake import connector

    if snowflake is None or not snowflake.schema:
        print("PHARMA_RX_DIAG transform skipped — no Snowflake schema in context")
        return

    fqn = (
        f"{snowflake.database}.{snowflake.schema}."
        if snowflake.database
        else f"{snowflake.schema}."
    )

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
        cur = conn.cursor()
        try:
            # Seed the base `dispenses` table (name matches the spec model).
            # Create UNQUOTED so Snowflake folds to upper-case — the compiler's
            # base-table SQL references the table name unquoted too, so both
            # resolve to the same upper-cased object.
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}dispenses ("
                "DISPENSE_ID NUMBER, SUBJECT_ID NUMBER, PRODUCT_ID NUMBER, "
                "UNITS NUMBER, DISPENSE_CHANNEL VARCHAR, PRESCRIBER_NPI VARCHAR"
                ")"
            )
            write_pandas(
                conn,
                dispenses,
                "DISPENSES",
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"PHARMA_RX_DIAG seeded {fqn}dispenses rows={len(dispenses)}")

            # Write the marker row (promised output model).
            managed = snowflake.full_table_name("dispenses_smoke_marker")
            marker_bare = managed.split(".")[-1].strip('"')
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": "n/a"}]),
                marker_bare,
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"PHARMA_RX_DIAG marker written to {managed}")

        finally:
            cur.close()
    finally:
        conn.close()
