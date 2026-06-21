"""Transform for the pharma-subjects-demo semantic-layer data product (self-seed).

This DP uses the template SELF-SEED deploy pattern (MESH_DESIGN.md § "Per-DP
authoring spec") — NOT the facade. Three jobs, all in this DP's OWN Snowflake
schema:

1.  Write a one-row marker table (``subjects_marker``) — the single promised
    output model — so the storage port's produce-verification passes without
    promising the base table itself.
2.  Seed this DP's OWN ``SUBJECTS`` base table (CREATE + INSERT) — the subject
    spine the semantic layer reads. Self-contained: no dependency on any other
    DP's schema or pre-existing data.
3.  Provision a SINGLE-TABLE ``SUBJECTS_SEMANTIC`` view over ``SUBJECTS`` ONLY.

CRITICAL: the view DDL is HAND-AUTHORED and references ONLY this DP's own
``SUBJECTS`` table. We deliberately do NOT call the compiler's
``native_semantic_view_ddl`` / ``plain_view_ddl``: when a registry has a cross-DP
join those emit a JOIN to a crosswalk table in ANOTHER DP's schema, and the
``CREATE VIEW`` binds the missing object → the transform fails → the DP goes
``Failed`` (this is what broke pharma-labs-demo). The subjects spine has no joins
today, but hand-authoring the single-table view keeps it unconditionally safe.

The transform also makes the ``**/*.py`` glob bundle registry.py / tools.py into
the image so the extracted rpc tool scripts can import them at runtime.
"""

from nxd.data_product.context import Snowflake


def transform(snowflake: Snowflake) -> None:
    import pandas as pd
    from snowflake import connector
    from snowflake.connector.pandas_tools import write_pandas

    from registry import REGISTRY
    from nxd.experimental.semantic.dialect import SnowflakeDialect

    if snowflake is None or not snowflake.schema:
        print("SUBJECTS_DIAG skipped — no Snowflake schema in context")
        return

    fqn = (
        f"{snowflake.database}.{snowflake.schema}."
        if snowflake.database
        else f"{snowflake.schema}."
    )
    view_name = SnowflakeDialect.default_view_name(REGISTRY)

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
            # 1) Marker (the promised output model).
            managed = snowflake.full_table_name("subjects_marker")
            marker_bare = managed.split(".")[-1].strip('"')
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": view_name}]),
                marker_bare,
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SUBJECTS_DIAG marker written to {managed}")

            # 2) Seed this DP's OWN subject-spine base table. Created UNQUOTED so
            # Snowflake folds it to upper-case, matching the hand-authored view's
            # unquoted `FROM SUBJECTS`.
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}SUBJECTS "
                "(SUBJECT_ID NUMBER, SUBJECT_COUNTRY VARCHAR, SUBJECT_MRN VARCHAR)"
            )
            write_pandas(
                conn,
                subjects,
                "SUBJECTS",
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SUBJECTS_DIAG seeded {fqn}SUBJECTS rows={len(subjects)}")

            # 3) Hand-authored SINGLE-TABLE semantic view over SUBJECTS ONLY.
            # NOT compiler-generated — no cross-DP JOIN is ever emitted.
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{view_name} AS "
                "SELECT SUBJECT_ID AS SUBJECT_ID, "
                "SUBJECT_COUNTRY AS SUBJECT_COUNTRY, "
                "SUBJECT_MRN AS SUBJECT_MRN "
                f"FROM {fqn}SUBJECTS"
            )
            print(f"SUBJECTS_DIAG provisioned single-table VIEW {fqn}{view_name}")
        finally:
            cur.close()
    finally:
        conn.close()
