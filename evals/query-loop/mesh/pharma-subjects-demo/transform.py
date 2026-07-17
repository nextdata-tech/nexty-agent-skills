"""Transform for pharma-subjects-demo — the SUBJECT SPINE of the mesh (self-seeded).

Two jobs, all in this DP's OWN Snowflake schema:

1.  Seed the base table (``subjects``) the semantic MCP tools read. Self-contained:
    no dependency on any other DP's schema or pre-existing data. CREATE OR REPLACE
    so re-runs are idempotent. The table is created UNQUOTED so Snowflake folds it
    to upper-case — the compiler's base-table SQL references the table name unquoted
    too, so both resolve to the same upper-cased object.
2.  Write a one-row marker table (``subjects_smoke_marker``) — the primary promised
    output model — so the storage port's produce-verification passes.

The semantic-view provisioning from the old registry.py/provision.py-based
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
        print("SUBJECTS_DIAG skipped — no Snowflake schema in context")
        return

    fqn = (
        f"{snowflake.database}.{snowflake.schema}."
        if snowflake.database
        else f"{snowflake.schema}."
    )

    subjects = pd.DataFrame(
        [
            {"SUBJECT_ID": 1, "SUBJECT_COUNTRY": "US", "SUBJECT_MRN": "MRN-0001"},
            {"SUBJECT_ID": 2, "SUBJECT_COUNTRY": "US", "SUBJECT_MRN": "MRN-0002"},
            {"SUBJECT_ID": 3, "SUBJECT_COUNTRY": "DE", "SUBJECT_MRN": "MRN-0003"},
            {"SUBJECT_ID": 4, "SUBJECT_COUNTRY": "DE", "SUBJECT_MRN": "MRN-0004"},
            {"SUBJECT_ID": 5, "SUBJECT_COUNTRY": "FR", "SUBJECT_MRN": "MRN-0005"},
            {"SUBJECT_ID": 6, "SUBJECT_COUNTRY": "BE", "SUBJECT_MRN": "MRN-0006"},
            {"SUBJECT_ID": 7, "SUBJECT_COUNTRY": "BE", "SUBJECT_MRN": "MRN-0007"},
            {"SUBJECT_ID": 8, "SUBJECT_COUNTRY": "NL", "SUBJECT_MRN": "MRN-0008"},
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
            # Seed the base table (name matches the spec model).
            # Create UNQUOTED so Snowflake folds to upper-case — the compiler's
            # base-table SQL references the table name unquoted too, so both
            # resolve to the same upper-cased object.
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}subjects "
                "(SUBJECT_ID NUMBER, SUBJECT_COUNTRY VARCHAR, SUBJECT_MRN VARCHAR)"
            )
            write_pandas(
                conn,
                subjects,
                "SUBJECTS",
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SUBJECTS_DIAG seeded {fqn}subjects rows={len(subjects)}")

            # Write the marker row (promised output model).
            managed = snowflake.full_table_name("subjects_smoke_marker")
            marker_bare = managed.split(".")[-1].strip('"')
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": "n/a"}]),
                marker_bare,
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SUBJECTS_DIAG marker written to {managed}")

        finally:
            cur.close()
    finally:
        conn.close()
