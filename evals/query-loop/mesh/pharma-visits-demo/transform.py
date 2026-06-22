"""Transform for the pharma-visits (DP_VISITS) semantic-layer data product.

SELF-SEED pattern (mirrors the deployable-dp template). Three jobs, all in this
DP's OWN Snowflake schema:

1.  Write a one-row marker table (``pharma_visits_marker``) — the single
    promised output model — so the storage port's produce-verification passes
    without promising the query tables themselves.
2.  Seed the base fact table (``visits``) the semantic layer reads.
    Self-contained: no dependency on any other DP's schema or data.
3.  Provision a SINGLE-TABLE ``VISITS_SEMANTIC`` view over ``visits`` ONLY.

CRITICAL — cross-DP view-DDL ban: this DP's registry declares a MANY_TO_ONE
join from ``visits`` to ``site_subjects`` (a crosswalk hub OWNED by DP_SITES, in
a DIFFERENT Snowflake schema). The compiler's ``native_semantic_view_ddl`` /
``plain_view_ddl`` would emit a ``JOIN site_subjects`` into the view DDL — that
binds an object that does NOT exist in this schema → ``CREATE VIEW`` fails →
the DP goes ``Failed`` (this is exactly what broke pharma-labs-demo). So we do
NOT call the compiler here; the single-table view is hand-authored over this
DP's own ``visits`` table. Cross-DP joins resolve at QUERY time via the live
mesh, not at view-creation time.

The transform also makes the ``**/*.py`` glob bundle registry.py / tools.py
into the image so the extracted rpc tool scripts can import them at runtime.
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
    # VISITS_SEMANTIC (first model "visits" upper + _SEMANTIC).
    view_name = SnowflakeDialect.default_view_name(REGISTRY)

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
        cur = conn.cursor()
        try:
            # 1) Marker (the promised output model).
            managed = snowflake.full_table_name("pharma_visits_marker")
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

            # 2) Seed the base fact table. Created UNQUOTED so Snowflake folds to
            # upper-case, matching the hand-authored view DDL below.
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}visits ("
                "VISIT_ID NUMBER, SUBJECT_ID NUMBER, VISIT_TYPE VARCHAR, DURATION_MIN FLOAT)"
            )
            write_pandas(
                conn,
                visits,
                "VISITS",
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG seeded {fqn}visits rows={len(visits)}")

            # 3) Hand-authored SINGLE-TABLE semantic view over THIS DP's own
            # `visits` table ONLY. Deliberately NOT using the compiler's
            # native_/plain_view_ddl — the registry's cross-DP join to
            # site_subjects would otherwise emit a JOIN into a missing object.
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{view_name} AS "
                "SELECT VISIT_ID AS VISIT_ID, "
                "SUBJECT_ID AS SUBJECT_ID, "
                "VISIT_TYPE AS VISIT_TYPE, "
                "DURATION_MIN AS DURATION_MIN "
                f"FROM {fqn}visits"
            )
            print(
                f"SEMVIEW_DIAG single-table OK provisioned VIEW {fqn}{view_name}"
            )
        finally:
            cur.close()
    finally:
        conn.close()
