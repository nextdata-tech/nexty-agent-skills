"""Transform for pharma-rx-demo (DP_RX) — TRANSFORM-SEED pattern.

Seeds this DP's OWN base table (`DISPENSES`) + the marker + the single-table
semantic view (`DISPENSES_SEMANTIC`) in this DP's Snowflake schema, in ONE
transform pass. This is the proven `pharma-subjects-demo` pattern: output-port
promise verification does NOT run before the transform (only input *expectations*
verify early), so a transform-seed deploys green in one launch.

The `.transform()` is also what bundles the sibling `registry.py` / `tools.py`
modules into the image (the `**/*.py` glob runs on the transform/compute path).

CRITICAL: the single-table view references ONLY this DP's own `DISPENSES` table —
NEVER a cross-DP crosswalk. Cross-DP joins (to site_subjects / products) resolve
at QUERY time via the live mesh, not at view creation.
"""

import pandas as pd
from nxd.data_product.context import Snowflake

_VIEW_NAME = "DISPENSES_SEMANTIC"  # = SnowflakeDialect.default_view_name(REGISTRY) for model `dispenses`


def transform(snowflake: Snowflake) -> None:
    from snowflake import connector
    from snowflake.connector.pandas_tools import write_pandas

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
            # 0) Marker (the promised output model) so the storage port verifies.
            managed = snowflake.full_table_name("pharma_rx_marker")
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": _VIEW_NAME}]),
                managed.split(".")[-1].strip('"'),
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"PHARMA_RX_DIAG marker written to {managed}")

            # 1) Seed this DP's OWN base fact table (grain: DISPENSE_ID).
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

            # 2) Single-table semantic view over DISPENSES only. Cross-DP joins
            # (site_subjects / products) resolve at QUERY time via the live mesh.
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS "
                "SELECT "
                "DISPENSE_ID AS DISPENSE_ID, "
                "SUBJECT_ID AS SUBJECT_ID, "
                "PRODUCT_ID AS PRODUCT_ID, "
                "UNITS AS UNITS, "
                "DISPENSE_CHANNEL AS DISPENSE_CHANNEL, "
                "PRESCRIBER_NPI AS PRESCRIBER_NPI "
                f"FROM {fqn}DISPENSES"
            )
            print(f"PHARMA_RX_DIAG provisioned single-table VIEW {fqn}{_VIEW_NAME}")
        finally:
            cur.close()
    finally:
        conn.close()
