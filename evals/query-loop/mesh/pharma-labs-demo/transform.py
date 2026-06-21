"""Transform for the pharma-labs (DP_LABS) semantic-layer data product.

SELF-SEED deploy pattern (MESH_DESIGN.md). Three jobs, all in this DP's OWN
Snowflake schema — self-contained, no dependency on any other DP's schema:

1.  Seed the base table ``ASSAYS`` (CREATE + INSERT) — the single promised
    output model — so the storage port's produce-verification passes.
2.  Provision a SINGLE-TABLE ``ASSAYS_SEMANTIC`` view over ``ASSAYS`` only.

CRITICAL: the view DDL references ONLY this DP's own ``ASSAYS`` table. We do
NOT call ``native_semantic_view_ddl`` / ``plain_view_ddl`` from the compiler:
this DP's registry declares a MANY_TO_ONE join to ``site_subjects`` (owned by
DP_SITES), and the compiler would emit that JOIN into the CREATE VIEW — binding
a crosswalk table that lives in ANOTHER DP's schema → the view creation fails at
deploy and the DP goes Failed. That was the original pharma-labs-demo break.
The cross-DP join resolves at QUERY time across the live mesh, not here. So the
view is hand-authored single-table.

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
    # Single-table semantic view name: <FIRST_MODEL_UPPER>_SEMANTIC → ASSAYS_SEMANTIC.
    view_name = SnowflakeDialect.default_view_name(REGISTRY)

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
            # 1) Seed the ASSAYS base table (the promised output model).
            # Create UNQUOTED so Snowflake folds to upper-case, matching the
            # unquoted references in the hand-authored view DDL below.
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}assays ("
                "ASSAY_ID NUMBER, SUBJECT_ID NUMBER, ASSAY_TYPE VARCHAR, TITER FLOAT)"
            )
            write_pandas(
                conn,
                assays,
                "ASSAYS",
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG seeded {fqn}assays rows={len(assays)}")

            # 2) Single-table semantic view over THIS DP's own ASSAYS table only.
            # NO JOIN to site_subjects (that crosswalk lives in DP_SITES' schema;
            # the cross-DP join resolves at query time, not in this CREATE VIEW).
            view_sql = (
                f"CREATE OR REPLACE VIEW {fqn}{view_name} AS "
                "SELECT ASSAY_ID, SUBJECT_ID, ASSAY_TYPE, TITER "
                f"FROM {fqn}assays"
            )
            cur.execute(view_sql)
            print(
                f"SEMVIEW_DIAG single-table OK provisioned VIEW {fqn}{view_name} "
                "(no cross-DP join)"
            )
        finally:
            cur.close()
    finally:
        conn.close()
