"""Transform for pharma-labs-demo — fact #2 (assays) of the pharma mesh.

Two jobs, all in this DP's OWN Snowflake schema:

1.  Seed the small base table (``ASSAYS``) the semantic MCP tools read.
    Self-contained: no dependency on any other DP's schema or pre-existing
    data. CREATE OR REPLACE so re-runs are idempotent.
2.  Write a one-row marker table (``assays_smoke_marker``) — the primary
    promised output model — so the storage port's produce-verification passes.

The semantic view provisioning from the old registry.py / provision.py
implementation is removed. The auto-generated ``run_semantic_query`` (wired by
``.semantic_tools()``) compiles governed SQL against the base table directly,
reading the kernel-delivered ``<root>/.nxd/semantic/<model>.json`` payloads. No
pre-provisioned view is required.
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

    # Self-seeded assays: grain ASSAY_ID, MANY assays per subject, assay_type
    # dimension + titer measure + the SUBJECT_ID join key (used only at query
    # time across the mesh — never joined in this single-table view).
    assays = pd.DataFrame(
        [
            {"ASSAY_ID": 1001, "SUBJECT_ID": 1, "ASSAY_TYPE": "ELISA", "TITER": 120.0},
            {"ASSAY_ID": 1002, "SUBJECT_ID": 1, "ASSAY_TYPE": "PCR", "TITER": 80.0},
            {"ASSAY_ID": 1003, "SUBJECT_ID": 2, "ASSAY_TYPE": "ELISA", "TITER": 200.0},
            {"ASSAY_ID": 1004, "SUBJECT_ID": 2, "ASSAY_TYPE": "titration", "TITER": 95.0},
            {"ASSAY_ID": 1005, "SUBJECT_ID": 3, "ASSAY_TYPE": "ELISA", "TITER": 50.0},
            {"ASSAY_ID": 1006, "SUBJECT_ID": 3, "ASSAY_TYPE": "PCR", "TITER": 300.0},
            {"ASSAY_ID": 1007, "SUBJECT_ID": 4, "ASSAY_TYPE": "titration", "TITER": 150.0},
            {"ASSAY_ID": 1008, "SUBJECT_ID": 5, "ASSAY_TYPE": "ELISA", "TITER": 175.0},
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
            # upper-cased object.
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}assays "
                "(ASSAY_ID NUMBER, SUBJECT_ID NUMBER, ASSAY_TYPE VARCHAR, TITER FLOAT)"
            )
            write_pandas(
                conn,
                assays,
                "ASSAYS",
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG seeded {fqn}assays rows={len(assays)}")

            # Write the marker row (promised output model).
            managed = snowflake.full_table_name("assays_smoke_marker")
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
