"""Transform for pharma-visits-demo — fact #1 (clinical visits) of the mesh.

Seeds this DP's OWN base table (`VISITS`) + the marker + the single-table
semantic view (`VISITS_SEMANTIC`) in this DP's Snowflake schema, in ONE
transform pass. This is the proven transform-seed pattern (mirrors
pharma-subjects-demo): output-port promise verification does NOT run before the
transform, so a transform-seed deploys green in one launch.

The `.transform()` is also what bundles the sibling `registry.py` / `tools.py`
modules into the image (the `**/*.py` glob runs on the transform/compute path).

CRITICAL — cross-DP view-DDL ban: this DP's registry declares a MANY_TO_ONE
join from `visits` to `site_subjects` (a crosswalk hub OWNED by DP_SITES, in a
DIFFERENT Snowflake schema). The compiler's view DDL would emit a
`JOIN site_subjects` that binds an object not present in this schema. So the
single-table view is hand-authored over this DP's OWN `visits` table ONLY;
cross-DP joins resolve at QUERY time.
"""

import pandas as pd
from nxd.data_product.context import Snowflake

_VIEW_NAME = "VISITS_SEMANTIC"  # = SnowflakeDialect.default_view_name(REGISTRY) for model `visits`


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
            # 0) Marker (the promised output model) so the storage port verifies.
            managed = snowflake.full_table_name("pharma_visits_marker")
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": _VIEW_NAME}]),
                managed.split(".")[-1].strip('"'),
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG marker written to {managed}")

            # 1) Seed this DP's OWN visits fact table (queried by the view).
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}VISITS "
                "(VISIT_ID NUMBER, SUBJECT_ID NUMBER, VISIT_TYPE VARCHAR, DURATION_MIN FLOAT)"
            )
            write_pandas(conn, visits, "VISITS",
                         database=snowflake.database, schema=snowflake.schema)
            print(f"SEMVIEW_DIAG seeded {fqn}VISITS rows={len(visits)}")

            # 2) Single-table semantic view over THIS DP's own `visits` table
            # ONLY. Deliberately NOT the compiler's view DDL — the registry's
            # cross-DP join to site_subjects would otherwise emit a JOIN into a
            # missing object.
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS "
                "SELECT VISIT_ID AS VISIT_ID, "
                "SUBJECT_ID AS SUBJECT_ID, "
                "VISIT_TYPE AS VISIT_TYPE, "
                "DURATION_MIN AS DURATION_MIN "
                f"FROM {fqn}VISITS"
            )
            print(f"SEMVIEW_DIAG provisioned single-table VIEW {fqn}{_VIEW_NAME}")
        finally:
            cur.close()
    finally:
        conn.close()
