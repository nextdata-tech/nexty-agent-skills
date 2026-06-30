"""Transform for pharma-visits-demo — fact #1 (clinical visits) of the mesh.

Two jobs, all in this DP's OWN Snowflake schema:

1.  Seed the ``visits`` base table the semantic MCP tools read. Self-contained:
    one row per clinical visit, MANY visits per subject. SUBJECT_ID is the join
    key into the crosswalk hub (resolved at query time, NOT here). CREATE OR
    REPLACE so re-runs are idempotent.
2.  Write a one-row marker table (``visits_smoke_marker``) — the promised output
    model — so the storage port's produce-verification passes.

The semantic view provisioning from the old registry.py/provision.py-based
implementation is removed. The auto-generated ``run_semantic_query`` (from
``nxd.experimental.semantic.entrypoints``) compiles governed SQL against the base
table directly, reading the kernel-delivered ``<root>/.nxd/semantic/<model>.json``
payloads. No pre-provisioned view is required.
"""

from nxd.data_product.context import Snowflake


def transform(snowflake: Snowflake) -> None:
    import pandas as pd
    from snowflake.connector.pandas_tools import write_pandas

    from snowflake import connector

    if snowflake is None or not snowflake.schema:
        print("SEMVIEW_DIAG skipped — no Snowflake schema in context")
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
            # Seed the base table (name matches the spec model). Create UNQUOTED
            # so Snowflake folds to upper-case — the compiler's base-table SQL
            # references the table name unquoted too, so both resolve to the same
            # upper-cased objects.
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}visits "
                "(VISIT_ID NUMBER, SUBJECT_ID NUMBER, VISIT_TYPE VARCHAR, DURATION_MIN FLOAT)"
            )
            write_pandas(
                conn,
                visits,
                "VISITS",
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG seeded {fqn}visits rows={len(visits)}")

            # Write the marker row (promised output model).
            managed = snowflake.full_table_name("visits_smoke_marker")
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
