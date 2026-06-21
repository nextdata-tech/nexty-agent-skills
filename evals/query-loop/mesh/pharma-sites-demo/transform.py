"""Transform for DP_SITES (pharma-sites-demo) — SELF-SEED, NOT facade.

The nxd validator HARD-REJECTS `.transform()` + `storage().as_view(...)` together
(_validate_facade_outputs), and the rpc-tool sibling bundling (`**/*.py` glob)
only fires when a transform exists. So this DP mirrors the deployable-dp template:
the post-verify transform SELF-SEEDS this DP's OWN base tables and provisions a
single-table semantic view. There is no facade.

Three jobs, all in this DP's OWN Snowflake schema:

1.  Write a one-row marker table (``site_provision_marker``) — the single
    promised output model — so the storage port's produce-verification passes.
2.  Seed this DP's OWN base tables (``SITES`` dimension + ``SITE_SUBJECTS``
    crosswalk) into the DP's schema. Self-contained: no dependency on any other
    DP's schema.
3.  Provision a SINGLE-TABLE ``<MODEL>_SEMANTIC`` view that references ONLY this
    DP's own tables.

CRITICAL — do NOT call ``native_semantic_view_ddl`` / ``plain_view_ddl``: the
registry declares a cross-DP MANY_TO_ONE join (``site_subjects`` -> ``subjects``,
the subject spine owned by DP_REGISTRY). The compiler would emit a JOIN to the
``subjects`` crosswalk target that lives in ANOTHER DP's schema, so the
``CREATE VIEW`` binds a missing object and the transform fails at deploy (this is
exactly what broke pharma-labs-demo). The single-table view below is hand-authored
and references only ``SITES`` / ``SITE_SUBJECTS`` in this DP's own schema. Cross-DP
joins resolve at QUERY time via the live mesh, not at view-creation time.

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
        print("SEMVIEW_DIAG skipped — no Snowflake schema in context")
        return

    fqn = (
        f"{snowflake.database}.{snowflake.schema}."
        if snowflake.database
        else f"{snowflake.schema}."
    )
    view_name = SnowflakeDialect.default_view_name(REGISTRY)

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
    site_subjects = pd.DataFrame(
        [
            {"SITE_ID": 1, "SUBJECT_ID": 101},
            {"SITE_ID": 1, "SUBJECT_ID": 102},
            {"SITE_ID": 2, "SUBJECT_ID": 102},
            {"SITE_ID": 2, "SUBJECT_ID": 103},
            {"SITE_ID": 3, "SUBJECT_ID": 104},
            {"SITE_ID": 3, "SUBJECT_ID": 105},
            {"SITE_ID": 4, "SUBJECT_ID": 105},
            {"SITE_ID": 5, "SUBJECT_ID": 106},
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
            managed = snowflake.full_table_name("site_provision_marker")
            marker_bare = managed.split(".")[-1].strip('"')
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": view_name}]),
                marker_bare,
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG marker written to {managed}")

            # 2) Seed this DP's OWN base tables. Create UNQUOTED so Snowflake folds
            #    to upper-case, matching the unquoted references in the view below.
            for name, df, cols in [
                ("sites", sites, "SITE_ID NUMBER, SITE_REGION VARCHAR"),
                ("site_subjects", site_subjects, "SITE_ID NUMBER, SUBJECT_ID NUMBER"),
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

            # 3) Hand-authored SINGLE-TABLE semantic view over THIS DP's own tables
            #    only. Do NOT use the compiler DDL helpers — the registry has a
            #    cross-DP join (site_subjects -> subjects, owned by DP_REGISTRY) and
            #    they would emit a JOIN to a table in another DP's schema, failing
            #    CREATE VIEW at deploy. The crosswalk grain (SITE_ID, SUBJECT_ID)
            #    joined to its OWN site dimension is fully resolvable here; the
            #    cross-DP subject join resolves at query time via the live mesh.
            view_ddl = (
                f"CREATE OR REPLACE VIEW {fqn}{view_name} AS\n"
                f"SELECT\n"
                f"    ss.SITE_ID      AS SITE_ID,\n"
                f"    ss.SUBJECT_ID   AS SUBJECT_ID,\n"
                f"    s.SITE_REGION   AS SITE_REGION\n"
                f"FROM {fqn}site_subjects AS ss\n"
                f"LEFT JOIN {fqn}sites AS s\n"
                f"    ON ss.SITE_ID = s.SITE_ID"
            )
            cur.execute(view_ddl)
            print(
                f"SEMVIEW_DIAG single-table OK provisioned VIEW {fqn}{view_name} "
                f"(this DP's own SITES / SITE_SUBJECTS only)"
            )
        finally:
            cur.close()
    finally:
        conn.close()
