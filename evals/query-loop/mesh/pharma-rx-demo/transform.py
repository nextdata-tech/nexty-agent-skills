"""Transform for the pharma-rx-demo (DP_RX) semantic-layer data product.

SELF-SEED deploy pattern (like ``deployable-dp/`` — NOT facade). Three jobs, all
in this DP's OWN Snowflake schema:

1.  Write a one-row marker table (``pharma_rx_marker``) — the single promised
    output model — so the storage port's produce-verification passes without
    promising the query tables themselves.
2.  Seed this DP's OWN base fact table (``DISPENSES``) the semantic layer reads.
    Self-contained: no dependency on any other DP's schema or pre-existing data.
3.  Provision the single-table ``DISPENSES_SEMANTIC`` view over that local table.

CRITICAL (the pharma-labs-demo break): the registry declares cross-DP N:1 joins
to ``site_subjects`` / ``products`` (owned by other DPs). We must NOT call the
compiler's ``native_semantic_view_ddl`` / ``plain_view_ddl`` here — those emit a
JOIN to crosswalk tables that live in ANOTHER DP's schema, so ``CREATE VIEW``
binds a missing object and the transform FAILS at deploy. The single-table view
below is HAND-AUTHORED and references ONLY this DP's own ``DISPENSES`` table.
Cross-DP joins resolve at QUERY time via the live mesh, not at view creation.

The transform also makes the ``**/*.py`` glob bundle registry.py / tools.py into
the image so the extracted rpc tool scripts can import them at runtime.
"""

from nxd.data_product.context import Snowflake


def transform(snowflake: Snowflake) -> None:
    import pandas as pd
    from snowflake.connector.pandas_tools import write_pandas

    from registry import REGISTRY
    from nxd.experimental.semantic.dialect import SnowflakeDialect
    from snowflake import connector

    if snowflake is None or not snowflake.schema:
        print("PHARMA_RX_DIAG skipped — no Snowflake schema in context")
        return

    fqn = (
        f"{snowflake.database}.{snowflake.schema}."
        if snowflake.database
        else f"{snowflake.schema}."
    )
    # <FIRST_MODEL_UPPER>_SEMANTIC → DISPENSES_SEMANTIC. Derived (not literal) so
    # it stays in lockstep with run_semantic_query's view-name resolution.
    view_name = SnowflakeDialect.default_view_name(REGISTRY)

    dispenses = pd.DataFrame(
        [
            {
                "DISPENSE_ID": 1,
                "SUBJECT_ID": 1,
                "PRODUCT_ID": 10,
                "UNITS": 30,
                "DISPENSE_CHANNEL": "retail",
                "PRESCRIBER_NPI": "1234567890",
            },
            {
                "DISPENSE_ID": 2,
                "SUBJECT_ID": 1,
                "PRODUCT_ID": 11,
                "UNITS": 60,
                "DISPENSE_CHANNEL": "mail-order",
                "PRESCRIBER_NPI": "1234567890",
            },
            {
                "DISPENSE_ID": 3,
                "SUBJECT_ID": 2,
                "PRODUCT_ID": 10,
                "UNITS": 30,
                "DISPENSE_CHANNEL": "retail",
                "PRESCRIBER_NPI": "9876543210",
            },
            {
                "DISPENSE_ID": 4,
                "SUBJECT_ID": 3,
                "PRODUCT_ID": 12,
                "UNITS": 90,
                "DISPENSE_CHANNEL": "specialty",
                "PRESCRIBER_NPI": "5556667770",
            },
            {
                "DISPENSE_ID": 5,
                "SUBJECT_ID": 3,
                "PRODUCT_ID": 12,
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
            # 1) Marker (the promised output model).
            managed = snowflake.full_table_name("pharma_rx_marker")
            marker_bare = managed.split(".")[-1].strip('"')
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": view_name}]),
                marker_bare,
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"PHARMA_RX_DIAG marker written to {managed}")

            # 2) Seed this DP's OWN base fact table (grain: DISPENSE_ID).
            # Create UNQUOTED so Snowflake folds to upper-case — the view DDL
            # references the table name unquoted too, so both resolve to the same
            # upper-cased object.
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}DISPENSES ("
                "DISPENSE_ID NUMBER, SUBJECT_ID NUMBER, PRODUCT_ID NUMBER, "
                "UNITS NUMBER, DISPENSE_CHANNEL VARCHAR, PRESCRIBER_NPI VARCHAR)"
            )
            write_pandas(
                conn,
                dispenses,
                "DISPENSES",
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"PHARMA_RX_DIAG seeded {fqn}DISPENSES rows={len(dispenses)}")

            # 3) Provision the SINGLE-TABLE semantic view over the LOCAL fact only.
            # HAND-AUTHORED — NOT the compiler's native/plain DDL, which would emit
            # JOINs to cross-DP crosswalk tables (site_subjects / products) that do
            # not exist in this schema and would fail CREATE VIEW. Cross-DP joins
            # resolve at QUERY time via the live mesh.
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{view_name} AS "
                "SELECT "
                "DISPENSE_ID AS DISPENSE_ID, "
                "SUBJECT_ID AS SUBJECT_ID, "
                "PRODUCT_ID AS PRODUCT_ID, "
                "UNITS AS UNITS, "
                "DISPENSE_CHANNEL AS DISPENSE_CHANNEL, "
                "PRESCRIBER_NPI AS PRESCRIBER_NPI "
                f"FROM {fqn}DISPENSES"
            )
            print(
                f"PHARMA_RX_DIAG single-table OK provisioned VIEW {fqn}{view_name}"
            )
        finally:
            cur.close()
    finally:
        conn.close()
