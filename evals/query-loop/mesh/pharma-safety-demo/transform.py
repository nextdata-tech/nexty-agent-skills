"""Transform for pharma-safety-demo — the FAR ADVERSE-EVENTS FACT of the mesh.

Seeds the ROWS of the promised `adverse_events` model's managed table. The table
STRUCTURE and the single-table `ADVERSE_EVENTS_SEMANTIC` view are created earlier
by the `@on_provision` hook (provision.py), which runs in Phase A before this
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
        print("SEMVIEW_DIAG transform skipped — no Snowflake schema in context")
        return

    # This DP's OWN adverse-events fact (one row per ae_id). IS_SERIOUS is the
    # boolean flag serious_ae_count CASE-sums over.
    adverse_events = pd.DataFrame(
        [
            {"AE_ID": 1001, "SUBJECT_ID": 1, "AE_TERM": "headache", "IS_SERIOUS": False},
            {"AE_ID": 1002, "SUBJECT_ID": 1, "AE_TERM": "nausea", "IS_SERIOUS": False},
            {"AE_ID": 1003, "SUBJECT_ID": 1, "AE_TERM": "anaphylaxis", "IS_SERIOUS": True},
            {"AE_ID": 1004, "SUBJECT_ID": 2, "AE_TERM": "headache", "IS_SERIOUS": False},
            {"AE_ID": 1005, "SUBJECT_ID": 2, "AE_TERM": "hepatic failure", "IS_SERIOUS": True},
            {"AE_ID": 1006, "SUBJECT_ID": 3, "AE_TERM": "rash", "IS_SERIOUS": False},
            {"AE_ID": 1007, "SUBJECT_ID": 3, "AE_TERM": "rash", "IS_SERIOUS": False},
            {"AE_ID": 1008, "SUBJECT_ID": 3, "AE_TERM": "cardiac arrest", "IS_SERIOUS": True},
            {"AE_ID": 1009, "SUBJECT_ID": 4, "AE_TERM": "dizziness", "IS_SERIOUS": False},
            {"AE_ID": 1010, "SUBJECT_ID": 5, "AE_TERM": "seizure", "IS_SERIOUS": True},
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
        managed = snowflake.full_table_name("adverse_events")
        # Truncate-and-load so repeated runs stay deterministic (the provision
        # hook created the table with CREATE TABLE IF NOT EXISTS, so it may
        # already hold rows from a prior run).
        cur = conn.cursor()
        try:
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
        finally:
            cur.close()
        write_pandas(conn, adverse_events, managed.split(".")[-1].strip('"'),
                     database=snowflake.database, schema=snowflake.schema)
        print(f"SEMVIEW_DIAG seeded {managed} rows={len(adverse_events)}")
    finally:
        conn.close()
