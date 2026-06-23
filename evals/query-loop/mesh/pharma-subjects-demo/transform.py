"""Transform for pharma-subjects-demo — the SUBJECT SPINE of the mesh.

Seeds this DP's OWN base table (`SUBJECTS`) + the single-table semantic view
(`SUBJECTS_SEMANTIC`) in this DP's Snowflake schema, in ONE transform pass. This
is the proven `hcp-master` pattern: output-port promise verification does NOT run
before the transform (only input *expectations* verify early, and this spine DP
has no inputs), so a transform-seed deploys green in one launch.

The `.transform()` is also what bundles the sibling `registry.py` / `tools.py`
modules into the image (the `**/*.py` glob runs on the transform/compute path).
"""

import pandas as pd
from nxd.data_product.context import Snowflake

_VIEW_NAME = "SUBJECTS_SEMANTIC"  # = SnowflakeDialect.default_view_name(REGISTRY) for model `subjects`


def transform(snowflake: Snowflake) -> None:
    from snowflake import connector
    from snowflake.connector.pandas_tools import write_pandas

    if snowflake is None or not snowflake.schema:
        print("SUBJECTS_DIAG transform skipped — no Snowflake schema in context")
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
            # 1) Seed the PROMISED `subjects` model's managed table. Using
            # full_table_name("subjects") writes to the exact table the storage
            # driver verifies the promise against (so produce-verification passes).
            managed = snowflake.full_table_name("subjects")
            cur.execute(
                f"CREATE OR REPLACE TABLE {managed} "
                "(SUBJECT_ID NUMBER, SUBJECT_COUNTRY VARCHAR, SUBJECT_MRN VARCHAR)"
            )
            write_pandas(conn, subjects, managed.split(".")[-1].strip('"'),
                         database=snowflake.database, schema=snowflake.schema)
            print(f"SUBJECTS_DIAG seeded {managed} rows={len(subjects)}")

            # 2) Single-table semantic view over the promised subjects table.
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS "
                "SELECT SUBJECT_ID AS SUBJECT_ID, "
                "SUBJECT_COUNTRY AS SUBJECT_COUNTRY, "
                "SUBJECT_MRN AS SUBJECT_MRN "
                f"FROM {managed}"
            )
            print(f"SUBJECTS_DIAG provisioned single-table VIEW {fqn}{_VIEW_NAME}")
        finally:
            cur.close()
    finally:
        conn.close()
