"""Provision hook for pharma-subjects-demo — seeds BEFORE promise verification.

The kernel runs output-port promise verification BEFORE the transform, so a
marker/base table seeded only in the transform does not exist yet at verify time
→ `Field MARKER_ID not found` → DP Failed. The provision function runs FIRST
(before storage-driver provisioning + before verify), so seeding here makes the
DP green in one launch. Wired via `.provision(script("provision.py"))` in spec.py.

SELF-CONTAINED — all imports are inline and it does NOT `import` any sibling
module (registry/tools/transform). The provision entrypoint is extracted into a
`provision/` subdir whose sys.path does not include the DP root, so a bare
`from registry import REGISTRY` would raise ModuleNotFoundError. The one value
that would come from the registry — the semantic view name — is the library
default `<FIRST_MODEL_UPPER>_SEMANTIC` = `SUBJECTS_SEMANTIC`, hardcoded here.
"""

from nxd import data_product
from nxd.data_product.context import Snowflake

_VIEW_NAME = "SUBJECTS_SEMANTIC"  # SnowflakeDialect.default_view_name(REGISTRY) for model `subjects`


@data_product.on_provision()
def provision(snowflake: Snowflake) -> None:
    import pandas as pd
    from snowflake import connector
    from snowflake.connector.pandas_tools import write_pandas

    if snowflake is None or not snowflake.schema:
        print("SUBJECTS_DIAG provision skipped — no Snowflake schema in context")
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
            # 1) Marker (the promised output model) — must exist before verify.
            managed = snowflake.full_table_name("subjects_marker")
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": _VIEW_NAME}]),
                managed.split(".")[-1].strip('"'),
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SUBJECTS_DIAG marker written to {managed}")

            # 2) Seed this DP's OWN subject-spine base table (unquoted -> upper).
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}SUBJECTS "
                "(SUBJECT_ID NUMBER, SUBJECT_COUNTRY VARCHAR, SUBJECT_MRN VARCHAR)"
            )
            write_pandas(conn, subjects, "SUBJECTS",
                         database=snowflake.database, schema=snowflake.schema)
            print(f"SUBJECTS_DIAG seeded {fqn}SUBJECTS rows={len(subjects)}")

            # 3) Hand-authored SINGLE-TABLE semantic view over SUBJECTS ONLY.
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS "
                "SELECT SUBJECT_ID AS SUBJECT_ID, "
                "SUBJECT_COUNTRY AS SUBJECT_COUNTRY, "
                "SUBJECT_MRN AS SUBJECT_MRN "
                f"FROM {fqn}SUBJECTS"
            )
            print(f"SUBJECTS_DIAG provisioned single-table VIEW {fqn}{_VIEW_NAME}")
        finally:
            cur.close()
    finally:
        conn.close()
