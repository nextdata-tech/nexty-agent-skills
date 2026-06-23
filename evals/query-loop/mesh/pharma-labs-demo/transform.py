"""Transform for pharma-labs-demo — fact #2 (assays) of the pharma mesh.

Seeds the ROWS of the promised `assays` model's managed table (`ASSAYS`). The
table STRUCTURE and the single-table `ASSAYS_SEMANTIC` view are created earlier
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

    # Self-seeded assays: grain ASSAY_ID, MANY assays per subject, assay_type
    # dimension + titer measure + the SUBJECT_ID join key (used only at query
    # time across the mesh — never joined in this single-table view).
    assays = pd.DataFrame(
        [
            {"ASSAY_ID": 1001, "SUBJECT_ID": 1, "ASSAY_TYPE": "ELISA", "TITER": 120.0},
            {"ASSAY_ID": 1002, "SUBJECT_ID": 1, "ASSAY_TYPE": "PCR", "TITER": 80.0},
            {"ASSAY_ID": 1003, "SUBJECT_ID": 2, "ASSAY_TYPE": "ELISA", "TITER": 200.0},
            {"ASSAY_ID": 1004, "SUBJECT_ID": 2, "ASSAY_TYPE": "titration", "TITER": 95.0},
            {"ASSAY_ID": 1005, "SUBJECT_ID": 3, "ASSAY_TYPE": "ELISA", "TITER": 50.0},
            {"ASSAY_ID": 1006, "SUBJECT_ID": 3, "ASSAY_TYPE": "PCR", "TITER": 300.0},
            {"ASSAY_ID": 1007, "SUBJECT_ID": 4, "ASSAY_TYPE": "titration", "TITER": 150.0},
            {"ASSAY_ID": 1008, "SUBJECT_ID": 5, "ASSAY_TYPE": "ELISA", "TITER": 175.0},
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
        managed = snowflake.full_table_name("assays")
        # Truncate-and-load so repeated runs stay deterministic (the provision
        # hook created the table with CREATE TABLE IF NOT EXISTS, so it may
        # already hold rows from a prior run).
        cur = conn.cursor()
        try:
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
        finally:
            cur.close()
        write_pandas(conn, assays, managed.split(".")[-1].strip('"'),
                     database=snowflake.database, schema=snowflake.schema)
        print(f"SEMVIEW_DIAG seeded {managed} rows={len(assays)}")
    finally:
        conn.close()
