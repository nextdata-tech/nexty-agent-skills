"""Transform for pharma-safety-demo — the FAR ADVERSE-EVENTS FACT of the mesh
(self-seeded).

Two jobs, all in this DP's OWN Snowflake schema:

1.  Seed the ``adverse_events`` base table the semantic MCP tools read.
    Self-contained: no dependency on any other DP's schema. CREATE OR REPLACE so
    re-runs are idempotent. Created UNQUOTED so Snowflake folds to upper-case —
    the compiler's base-table SQL references the table name unquoted too, so both
    resolve to the same upper-cased object.
2.  Write a one-row marker table (``adverse_events_smoke_marker``) — the primary
    promised output model — so the storage port's produce-verification passes.

The semantic view provisioning from the old registry.py-based implementation is
removed. The auto-generated ``run_semantic_query`` (wired by ``.semantic_tools()``)
compiles governed SQL against the base table directly, reading the kernel-delivered
``<root>/.nxd/semantic/<model>.json`` payloads. No pre-provisioned view is required.
"""

from nxd.data_product.context import Snowflake


def transform(snowflake: Snowflake) -> None:
    import pandas as pd
    from snowflake.connector.pandas_tools import write_pandas

    from snowflake import connector

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
            # Seed the base table (name matches the spec model). Create UNQUOTED so
            # Snowflake folds to upper-case — the compiler's base-table SQL
            # references the table name unquoted too, so both resolve to the same
            # upper-cased object.
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}adverse_events "
                "(AE_ID NUMBER, SUBJECT_ID NUMBER, AE_TERM VARCHAR, IS_SERIOUS BOOLEAN)"
            )
            write_pandas(
                conn,
                adverse_events,
                "ADVERSE_EVENTS",
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG seeded {fqn}adverse_events rows={len(adverse_events)}")

            # Write the marker row (promised output model).
            managed = snowflake.full_table_name("adverse_events_smoke_marker")
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
