"""Transform for pharma-sites-demo — the MANY_TO_MANY crosswalk HUB of the mesh.

Seeds this DP's OWN base tables (`SITES` + `SITE_SUBJECTS`) + the single-table
semantic view (`SITE_SUBJECTS_SEMANTIC`) in this DP's Snowflake schema, in ONE
transform pass. This is the proven `hcp-master` pattern: output-port promise
verification does NOT run before the transform (only input *expectations* verify
early), so a transform-seed deploys green in one launch.

The `.transform()` is also what bundles the sibling `registry.py` / `tools.py`
modules into the image (the `**/*.py` glob runs on the transform/compute path).

CRITICAL — the single-table view references ONLY this DP's own tables
(SITES / SITE_SUBJECTS). The registry declares a cross-DP MANY_TO_ONE join
(site_subjects -> subjects, owned by pharma-subjects-demo); a compiler-generated
view would emit a JOIN to a table in another DP's schema and fail CREATE VIEW at
deploy. The cross-DP subject join resolves at QUERY time via the live mesh.
"""

import pandas as pd
from nxd.data_product.context import Snowflake

_VIEW_NAME = "SITE_SUBJECTS_SEMANTIC"  # = SnowflakeDialect.default_view_name(REGISTRY) for model `site_subjects`


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
        cur = conn.cursor()
        try:
            # 1a) Seed the site DIMENSION (this DP's own table, referenced by the
            #     view's LEFT JOIN). Create UNQUOTED so Snowflake folds to
            #     upper-case, matching the unquoted references in the view below.
            cur.execute(f"CREATE OR REPLACE TABLE {fqn}sites (SITE_ID NUMBER, SITE_REGION VARCHAR)")
            write_pandas(
                conn,
                sites,
                "SITES",
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG seeded {fqn}sites rows={len(sites)}")

            # 1b) Seed the PROMISED `site_subjects` crosswalk model's MANAGED table.
            #     full_table_name("site_subjects") returns the exact table the
            #     storage driver verifies the promise against, so produce-
            #     verification passes against the REAL model.
            managed = snowflake.full_table_name("site_subjects")
            cur.execute(f"CREATE OR REPLACE TABLE {managed} (SITE_ID NUMBER, SUBJECT_ID NUMBER)")
            write_pandas(
                conn,
                site_subjects,
                managed.split(".")[-1].strip('"'),
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG seeded {managed} rows={len(site_subjects)}")

            # 2) Hand-authored SINGLE-TABLE semantic view over THIS DP's own tables
            #    only. Do NOT use the compiler DDL helpers — the registry has a
            #    cross-DP join (site_subjects -> subjects, owned by
            #    pharma-subjects-demo) and they would emit a JOIN to a table in
            #    another DP's schema, failing CREATE VIEW at deploy. The crosswalk
            #    grain (SITE_ID, SUBJECT_ID) joined to its OWN site dimension is
            #    fully resolvable here; the cross-DP subject join resolves at query
            #    time via the live mesh.
            view_ddl = (
                f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS\n"
                f"SELECT\n"
                f"    ss.SITE_ID      AS SITE_ID,\n"
                f"    ss.SUBJECT_ID   AS SUBJECT_ID,\n"
                f"    s.SITE_REGION   AS SITE_REGION\n"
                f"FROM {managed} AS ss\n"
                f"LEFT JOIN {fqn}sites AS s\n"
                f"    ON ss.SITE_ID = s.SITE_ID"
            )
            cur.execute(view_ddl)
            print(
                f"SEMVIEW_DIAG single-table OK provisioned VIEW {fqn}{_VIEW_NAME} "
                f"(this DP's own SITES / SITE_SUBJECTS only)"
            )
        finally:
            cur.close()
    finally:
        conn.close()
