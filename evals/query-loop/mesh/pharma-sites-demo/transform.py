"""Transform for pharma-sites-demo — the MANY_TO_MANY crosswalk HUB of the mesh.

Self-seeded (NEW .semantic_tools() pattern). Two jobs, all in this DP's OWN
Snowflake schema:

1.  Seed BOTH base tables — the site dimension (``sites``) and the crosswalk hub
    (``site_subjects``) — with ``CREATE OR REPLACE TABLE`` + ``write_pandas``.
    The names are UNQUOTED so Snowflake folds them to upper-case, matching the
    compiler's base-table SQL (which references the table names unquoted too), so
    both resolve to the same upper-cased objects.
2.  Write a one-row marker table (``sites_smoke_marker``) — the produce-verified
    promised model — via ``full_table_name(...)`` so the storage port's
    produce-verification passes.

The old registry.py / tools.py / provision.py modules and the single-table
semantic view are removed. The auto-generated ``run_semantic_query`` (wired by
``.semantic_tools()``) compiles governed SQL against the base tables directly,
reading the kernel-delivered ``<root>/.nxd/semantic/<model>.json`` payloads. No
pre-provisioned view is required.
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
        cur = conn.cursor()
        try:
            # Seed the two base tables (names match the spec models).
            # Create UNQUOTED so Snowflake folds to upper-case — the compiler's
            # base-table SQL references the table names unquoted too, so both
            # resolve to the same upper-cased objects.
            for name, df, cols in [
                ("sites", sites, "SITE_ID NUMBER, SITE_REGION VARCHAR"),
                (
                    "site_subjects",
                    site_subjects,
                    "SITE_ID NUMBER, SUBJECT_ID NUMBER",
                ),
            ]:
                cur.execute(f"CREATE OR REPLACE TABLE {fqn}{name} ({cols})")
                write_pandas(
                    conn,
                    df,
                    name.upper(),
                    database=snowflake.database,
                    schema=snowflake.schema,
                )
                print(f"SEMVIEW_DIAG seeded {fqn}{name} rows={len(df)}")

            # Write the marker row (produce-verified promised model).
            managed = snowflake.full_table_name("sites_smoke_marker")
            marker_bare = managed.split(".")[-1].strip('"')
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": "n/a"}]),
                marker_bare,
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG marker written to {managed}")
        finally:
            cur.close()
    finally:
        conn.close()
