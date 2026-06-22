"""Transform for the pharma-safety (DP_SAFETY) semantic-layer data product.

SELF-SEED deploy pattern (MESH_DESIGN.md). Three jobs, all in this DP's OWN
Snowflake schema:

1.  Write a one-row marker table (``pharma_safety_marker``) — the single
    promised output model — so the storage port's produce-verification passes
    without promising the query tables themselves.
2.  Seed this DP's OWN base table (``adverse_events``) the semantic layer reads.
    Self-contained: no dependency on any other DP's schema or pre-existing data.
3.  Provision a SINGLE-TABLE ``ADVERSE_EVENTS_SEMANTIC`` view over that one
    table — hand-authored, referencing ONLY this DP's own ``adverse_events``.

CRITICAL (MESH_DESIGN.md, the pharma-labs-demo break): this DP's registry has a
cross-DP MANY_TO_ONE join to ``site_subjects`` (owned by DP_SITES, lives in
ANOTHER schema). We therefore MUST NOT call the compiler's
``native_semantic_view_ddl`` / ``plain_view_ddl`` — those emit a JOIN to the
crosswalk table in the other DP's schema, so ``CREATE VIEW`` binds a missing
object and the transform fails → DP ``Failed``. The cross-DP join resolves at
QUERY time via the live mesh, not at view-creation time. We hand-author a
single-table view over ``adverse_events`` only. ``run_semantic_query`` reads the
base table directly for single-model selections and this view for single-hop
selections that stay within this DP.

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
    # ``<FIRST_MODEL_UPPER>_SEMANTIC`` -> ``ADVERSE_EVENTS_SEMANTIC``. Matches the
    # name run_semantic_query resolves via SnowflakeDialect.default_view_name.
    view_name = SnowflakeDialect.default_view_name(REGISTRY)

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
            # 1) Marker (the promised output model).
            managed = snowflake.full_table_name("pharma_safety_marker")
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

            # 2) Seed this DP's OWN base table. Create UNQUOTED so Snowflake folds
            #    to upper-case — the compiler references the table name unquoted
            #    too (`FROM adverse_events`), so both resolve to the same object.
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}adverse_events ("
                "AE_ID NUMBER, SUBJECT_ID NUMBER, AE_TERM VARCHAR, IS_SERIOUS BOOLEAN)"
            )
            write_pandas(
                conn,
                adverse_events,
                "ADVERSE_EVENTS",
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG seeded {fqn}adverse_events rows={len(adverse_events)}")

            # 3) Hand-authored SINGLE-TABLE semantic view over THIS DP's own table
            #    only. We deliberately DO NOT call native_semantic_view_ddl /
            #    plain_view_ddl: this registry's only join is the cross-DP N:1 to
            #    site_subjects (another DP's schema), and those helpers would emit
            #    a JOIN to a missing object → CREATE VIEW fails (the
            #    pharma-labs-demo break). The cross-DP join resolves at query time
            #    via the live mesh. Project the physical columns the registry's
            #    dimensions/metrics reference (AE_ID, SUBJECT_ID, AE_TERM,
            #    IS_SERIOUS).
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{view_name} AS\n"
                "SELECT\n"
                "  AE_ID AS AE_ID,\n"
                "  SUBJECT_ID AS SUBJECT_ID,\n"
                "  AE_TERM AS AE_TERM,\n"
                "  IS_SERIOUS AS IS_SERIOUS\n"
                f"FROM {fqn}adverse_events"
            )
            print(
                f"SEMVIEW_DIAG single-table OK provisioned VIEW {fqn}{view_name} "
                "(cross-DP join resolved at query time, not materialised)"
            )
        finally:
            cur.close()
    finally:
        conn.close()
