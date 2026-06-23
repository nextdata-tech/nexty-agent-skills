"""Transform for pharma-sites-demo — the MANY_TO_MANY crosswalk HUB of the mesh.

Seeds the ROWS of this DP's OWN base tables (`SITES` + the promised
`site_subjects` managed table). The table STRUCTURES and the single-table
`SITE_SUBJECTS_SEMANTIC` view are created earlier by the `@on_provision` hook
(provision.py), which runs in Phase A before this transform. This transform only
writes the data the output-port promise verifies.

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

    fqn = (
        f"{snowflake.database}.{snowflake.schema}."
        if snowflake.database
        else f"{snowflake.schema}."
    )

    # This DP's OWN base tables — the site dimension and the crosswalk hub.
    sites = pd.DataFrame(
        [
            {"SITE_ID": 1, "SITE_REGION": "NA"},
            {"SITE_ID": 2, "SITE_REGION": "NA"},
            {"SITE_ID": 3, "SITE_REGION": "EU"},
            {"SITE_ID": 4, "SITE_REGION": "EU"},
            {"SITE_ID": 5, "SITE_REGION": "APAC"},
        ]
    )
    # Crosswalk keyed on the SUBJECT_ID spine (1-8, owned by pharma-subjects-demo)
    # so the cross-DP joins (every fact -> site_subjects -> subjects) resolve at
    # query time. MANY_TO_MANY: subjects 2 and 5 enroll at two sites (fan-out).
    site_subjects = pd.DataFrame(
        [
            {"SITE_ID": 1, "SUBJECT_ID": 1},
            {"SITE_ID": 1, "SUBJECT_ID": 2},
            {"SITE_ID": 2, "SUBJECT_ID": 2},
            {"SITE_ID": 2, "SUBJECT_ID": 3},
            {"SITE_ID": 3, "SUBJECT_ID": 4},
            {"SITE_ID": 3, "SUBJECT_ID": 5},
            {"SITE_ID": 4, "SUBJECT_ID": 5},
            {"SITE_ID": 4, "SUBJECT_ID": 6},
            {"SITE_ID": 5, "SUBJECT_ID": 7},
            {"SITE_ID": 5, "SUBJECT_ID": 8},
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
        # 1a) Seed the site DIMENSION rows (table created by the provision hook).
        #     Truncate-and-load so repeated runs stay deterministic (the provision
        #     hook created the table with CREATE TABLE IF NOT EXISTS, so it may
        #     already hold rows from a prior run).
        cur = conn.cursor()
        try:
            cur.execute(f"TRUNCATE TABLE IF EXISTS {fqn}sites")
        finally:
            cur.close()
        write_pandas(
            conn,
            sites,
            "SITES",
            database=snowflake.database,
            schema=snowflake.schema,
        )
        print(f"SEMVIEW_DIAG seeded {fqn}sites rows={len(sites)}")

        # 1b) Seed the PROMISED `site_subjects` crosswalk model's MANAGED table.
        #     full_table_name("site_subjects") returns the exact table the storage
        #     driver verifies the promise against, so produce-verification passes
        #     against the REAL model.
        managed = snowflake.full_table_name("site_subjects")
        cur = conn.cursor()
        try:
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
        finally:
            cur.close()
        write_pandas(
            conn,
            site_subjects,
            managed.split(".")[-1].strip('"'),
            database=snowflake.database,
            schema=snowflake.schema,
        )
        print(f"SEMVIEW_DIAG seeded {managed} rows={len(site_subjects)}")
    finally:
        conn.close()
