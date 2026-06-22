"""Transform for pharma-labs-demo — fact #2 (assays) of the pharma mesh.

Seeds this DP's OWN base table (`ASSAYS`) + the marker (so the storage port
verifies) + the single-table semantic view (`ASSAYS_SEMANTIC`) in this DP's
Snowflake schema, in ONE transform pass. This is the proven `hcp-master` /
pharma-subjects-demo pattern: output-port promise verification does NOT block a
transform-seed, so a transform-seed deploys green in one launch.

The `.transform()` is also what bundles the sibling `registry.py` / `tools.py`
modules into the image (the `**/*.py` glob runs on the transform/compute path).

CRITICAL: the view DDL references ONLY this DP's own `ASSAYS` table. This DP's
registry declares a MANY_TO_ONE join to `site_subjects` (owned by DP_SITES);
emitting that JOIN into the CREATE VIEW would bind a crosswalk table that lives
in ANOTHER DP's schema → view creation fails at deploy. The cross-DP join
resolves at QUERY time across the live mesh, not here.
"""

import pandas as pd
from nxd.data_product.context import Snowflake

_VIEW_NAME = "ASSAYS_SEMANTIC"  # = SnowflakeDialect.default_view_name(REGISTRY) for model `assays`


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
            # 0) Marker (the promised output model) so the storage port verifies.
            managed = snowflake.full_table_name("assays_marker")
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": _VIEW_NAME}]),
                managed.split(".")[-1].strip('"'),
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG marker written to {managed}")

            # 1) Seed the ASSAYS base table (queried by the semantic view).
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}ASSAYS ("
                "ASSAY_ID NUMBER, SUBJECT_ID NUMBER, ASSAY_TYPE VARCHAR, TITER FLOAT)"
            )
            write_pandas(conn, assays, "ASSAYS",
                         database=snowflake.database, schema=snowflake.schema)
            print(f"SEMVIEW_DIAG seeded {fqn}ASSAYS rows={len(assays)}")

            # 2) Single-table semantic view over THIS DP's own ASSAYS table only.
            # NO JOIN to site_subjects (that crosswalk lives in DP_SITES' schema;
            # the cross-DP join resolves at query time, not in this CREATE VIEW).
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS "
                "SELECT ASSAY_ID AS ASSAY_ID, "
                "SUBJECT_ID AS SUBJECT_ID, "
                "ASSAY_TYPE AS ASSAY_TYPE, "
                "TITER AS TITER "
                f"FROM {fqn}ASSAYS"
            )
            print(f"SEMVIEW_DIAG provisioned single-table VIEW {fqn}{_VIEW_NAME}")
        finally:
            cur.close()
    finally:
        conn.close()
