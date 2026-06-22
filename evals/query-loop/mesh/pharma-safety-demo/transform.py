"""Transform for pharma-safety-demo — the FAR ADVERSE-EVENTS FACT of the mesh.

Seeds this DP's OWN base table (`ADVERSE_EVENTS`) + marker + the single-table
semantic view (`ADVERSE_EVENTS_SEMANTIC`) in this DP's Snowflake schema, in ONE
transform pass. This is the proven `pharma-subjects-demo` pattern: output-port
promise verification does NOT run before the transform (only input *expectations*
verify early), so a transform-seed deploys green in one launch.

The `.transform()` is also what bundles the sibling `registry.py` / `tools.py`
modules into the image (the `**/*.py` glob runs on the transform/compute path).

CRITICAL (MESH_DESIGN.md, the pharma-labs-demo break): this DP's registry has a
cross-DP MANY_TO_ONE join to `site_subjects` (owned by DP_SITES, lives in
ANOTHER schema). We therefore hand-author a SINGLE-TABLE view over
`adverse_events` only — we MUST NOT emit a JOIN to the crosswalk table in the
other DP's schema, or `CREATE VIEW` binds a missing object and the DP fails. The
cross-DP join resolves at QUERY time via the live mesh, not at view creation.
"""

import pandas as pd
from nxd.data_product.context import Snowflake

_VIEW_NAME = "ADVERSE_EVENTS_SEMANTIC"  # = SnowflakeDialect.default_view_name(REGISTRY) for model `adverse_events`


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
        cur = conn.cursor()
        try:
            # 0) Marker (the promised output model) so the storage port verifies.
            managed = snowflake.full_table_name("pharma_safety_marker")
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": _VIEW_NAME}]),
                managed.split(".")[-1].strip('"'),
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG marker written to {managed}")

            # 1) Seed this DP's OWN adverse-events base table (unquoted -> upper).
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}adverse_events "
                "(AE_ID NUMBER, SUBJECT_ID NUMBER, AE_TERM VARCHAR, IS_SERIOUS BOOLEAN)"
            )
            write_pandas(conn, adverse_events, "ADVERSE_EVENTS",
                         database=snowflake.database, schema=snowflake.schema)
            print(f"SEMVIEW_DIAG seeded {fqn}adverse_events rows={len(adverse_events)}")

            # 2) Hand-authored SINGLE-TABLE semantic view over ADVERSE_EVENTS ONLY.
            #    We deliberately DO NOT emit the cross-DP JOIN to site_subjects
            #    (another DP's schema) — that would bind a missing object and fail
            #    CREATE VIEW. The cross-DP join resolves at query time via the mesh.
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS "
                "SELECT AE_ID AS AE_ID, "
                "SUBJECT_ID AS SUBJECT_ID, "
                "AE_TERM AS AE_TERM, "
                "IS_SERIOUS AS IS_SERIOUS "
                f"FROM {fqn}adverse_events"
            )
            print(f"SEMVIEW_DIAG provisioned single-table VIEW {fqn}{_VIEW_NAME}")
        finally:
            cur.close()
    finally:
        conn.close()
