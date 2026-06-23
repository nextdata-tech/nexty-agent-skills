"""Transform for pharma-visits-demo — fact #1 (clinical visits) of the mesh.

Seeds the ROWS of the promised `visits` model's managed table. The table
STRUCTURE and the single-table `VISITS_SEMANTIC` view are created earlier by
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
        print("SEMVIEW_DIAG transform skipped — no Snowflake schema in context")
        return

    # One row per clinical visit; MANY visits per subject. SUBJECT_ID is the
    # join key into the crosswalk hub (resolved at query time, NOT here).
    visits = pd.DataFrame(
        [
            {"VISIT_ID": 1, "SUBJECT_ID": 1, "VISIT_TYPE": "screening", "DURATION_MIN": 45.0},
            {"VISIT_ID": 2, "SUBJECT_ID": 1, "VISIT_TYPE": "baseline", "DURATION_MIN": 30.0},
            {"VISIT_ID": 3, "SUBJECT_ID": 1, "VISIT_TYPE": "follow-up", "DURATION_MIN": 20.0},
            {"VISIT_ID": 4, "SUBJECT_ID": 2, "VISIT_TYPE": "screening", "DURATION_MIN": 50.0},
            {"VISIT_ID": 5, "SUBJECT_ID": 2, "VISIT_TYPE": "baseline", "DURATION_MIN": 25.0},
            {"VISIT_ID": 6, "SUBJECT_ID": 3, "VISIT_TYPE": "screening", "DURATION_MIN": 40.0},
            {"VISIT_ID": 7, "SUBJECT_ID": 3, "VISIT_TYPE": "follow-up", "DURATION_MIN": 15.0},
            {"VISIT_ID": 8, "SUBJECT_ID": 4, "VISIT_TYPE": "baseline", "DURATION_MIN": 35.0},
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
        managed = snowflake.full_table_name("visits")
        # Truncate-and-load so repeated runs stay deterministic (the provision
        # hook created the table with CREATE TABLE IF NOT EXISTS, so it may
        # already hold rows from a prior run).
        cur = conn.cursor()
        try:
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
        finally:
            cur.close()
        write_pandas(conn, visits, managed.split(".")[-1].strip('"'),
                     database=snowflake.database, schema=snowflake.schema)
        print(f"SEMVIEW_DIAG seeded {managed} rows={len(visits)}")
    finally:
        conn.close()
