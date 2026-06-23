"""Transform for pharma-subjects-demo — the SUBJECT SPINE of the mesh.

Seeds the ROWS of the promised `subjects` model's managed table. The table
STRUCTURE and the single-table `SUBJECTS_SEMANTIC` view are created earlier by
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
        print("SUBJECTS_DIAG transform skipped — no Snowflake schema in context")
        return

    subjects = pd.DataFrame(
        [
            {"SUBJECT_ID": 1, "SUBJECT_COUNTRY": "US", "SUBJECT_MRN": "MRN-0001"},
            {"SUBJECT_ID": 2, "SUBJECT_COUNTRY": "US", "SUBJECT_MRN": "MRN-0002"},
            {"SUBJECT_ID": 3, "SUBJECT_COUNTRY": "DE", "SUBJECT_MRN": "MRN-0003"},
            {"SUBJECT_ID": 4, "SUBJECT_COUNTRY": "DE", "SUBJECT_MRN": "MRN-0004"},
            {"SUBJECT_ID": 5, "SUBJECT_COUNTRY": "FR", "SUBJECT_MRN": "MRN-0005"},
            {"SUBJECT_ID": 6, "SUBJECT_COUNTRY": "BE", "SUBJECT_MRN": "MRN-0006"},
            {"SUBJECT_ID": 7, "SUBJECT_COUNTRY": "BE", "SUBJECT_MRN": "MRN-0007"},
            {"SUBJECT_ID": 8, "SUBJECT_COUNTRY": "NL", "SUBJECT_MRN": "MRN-0008"},
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
        managed = snowflake.full_table_name("subjects")
        # Truncate-and-load so repeated runs stay deterministic (the provision
        # hook created the table with CREATE TABLE IF NOT EXISTS, so it may
        # already hold rows from a prior run).
        cur = conn.cursor()
        try:
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
        finally:
            cur.close()
        write_pandas(conn, subjects, managed.split(".")[-1].strip('"'),
                     database=snowflake.database, schema=snowflake.schema)
        print(f"SUBJECTS_DIAG seeded {managed} rows={len(subjects)}")
    finally:
        conn.close()
