"""Pre-provision hook for pharma-subjects-demo — the SUBJECT SPINE of the mesh.

Provisions the serving objects in this DP's Snowflake schema BEFORE the
transform runs:

  1. ``CREATE TABLE IF NOT EXISTS`` the promised ``subjects`` model's managed
     table (structure only — the transform fills the rows).
  2. ``CREATE OR REPLACE VIEW SUBJECTS_SEMANTIC`` — the single-table semantic
     view the run_semantic_query compiler reads. Binding it here is safe because
     step 1 created the table object (the view references the object, not rows).

Lifecycle ordering: the ``@on_provision`` hook runs in Phase A, before the
transform. The output-port promise (rows present in the managed table) is
verified AFTER the transform, so provisioning structure here + seeding rows in
the transform satisfies the promise in one launch.

The hook receives the ``snowflake`` storage output port by parameter name (the
``ProvisionOutputPortArgumentProvider`` injects it as a typed ``Snowflake``
handle — same API the transform uses).
"""

from nxd import data_product
from nxd.data_product.context import Snowflake

_VIEW_NAME = "SUBJECTS_SEMANTIC"  # = SnowflakeDialect.default_view_name(REGISTRY) for model `subjects`


@data_product.on_provision()
def provision(snowflake: Snowflake) -> None:
    from snowflake import connector

    if snowflake is None or not snowflake.schema:
        print("SUBJECTS_DIAG provision skipped — no Snowflake schema in context")
        return

    fqn = (
        f"{snowflake.database}.{snowflake.schema}."
        if snowflake.database
        else f"{snowflake.schema}."
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
            # 1) Create the PROMISED `subjects` model's managed table (structure
            # only). full_table_name("subjects") is the exact table the storage
            # driver verifies the promise against; the transform writes the rows.
            managed = snowflake.full_table_name("subjects")
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {managed} "
                "(SUBJECT_ID NUMBER, SUBJECT_COUNTRY VARCHAR, SUBJECT_MRN VARCHAR)"
            )
            print(f"SUBJECTS_DIAG provisioned TABLE {managed}")

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


if __name__ == "__main__":
    data_product.provision()
