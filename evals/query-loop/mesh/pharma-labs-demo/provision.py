"""Pre-provision hook for pharma-labs-demo — fact #2 (assays) of the pharma mesh.

Provisions the serving objects in this DP's Snowflake schema BEFORE the
transform runs:

  1. ``CREATE TABLE IF NOT EXISTS`` the promised ``assays`` model's managed
     table (structure only — the transform fills the rows).
  2. ``CREATE OR REPLACE VIEW ASSAYS_SEMANTIC`` — the single-table semantic
     view the run_semantic_query compiler reads. Binding it here is safe because
     step 1 created the table object (the view references the object, not rows).

Lifecycle ordering: the ``@on_provision`` hook runs in Phase A, before the
transform. The output-port promise (rows present in the managed table) is
verified AFTER the transform, so provisioning structure here + seeding rows in
the transform satisfies the promise in one launch.

CRITICAL: the view DDL references ONLY this DP's own ``ASSAYS`` table. This DP's
registry declares a MANY_TO_ONE join to ``site_subjects`` (owned by DP_SITES);
emitting that JOIN into the CREATE VIEW would bind a crosswalk table that lives
in ANOTHER DP's schema → view creation fails at deploy. The cross-DP join
resolves at QUERY time across the live mesh, not here.

The hook receives the ``snowflake`` storage output port by parameter name (the
``ProvisionOutputPortArgumentProvider`` injects it as a typed ``Snowflake``
handle — same API the transform uses).
"""

from nxd import data_product
from nxd.data_product.context import Snowflake

_VIEW_NAME = "ASSAYS_SEMANTIC"  # = SnowflakeDialect.default_view_name(REGISTRY) for model `assays`


@data_product.on_provision()
def provision(snowflake: Snowflake) -> None:
    from snowflake import connector

    if snowflake is None or not snowflake.schema:
        print("SEMVIEW_DIAG provision skipped — no Snowflake schema in context")
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
            # 1) Create the PROMISED `assays` model's managed table (structure
            # only). full_table_name("assays") is the exact table the storage
            # driver verifies the promise against; the transform writes the rows.
            managed = snowflake.full_table_name("assays")
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {managed} ("
                "ASSAY_ID NUMBER, SUBJECT_ID NUMBER, ASSAY_TYPE VARCHAR, TITER FLOAT)"
            )
            print(f"SEMVIEW_DIAG provisioned TABLE {managed}")

            # 2) Single-table semantic view over the promised ASSAYS table only.
            # NO JOIN to site_subjects (that crosswalk lives in DP_SITES' schema;
            # the cross-DP join resolves at query time, not in this CREATE VIEW).
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS "
                "SELECT ASSAY_ID AS ASSAY_ID, "
                "SUBJECT_ID AS SUBJECT_ID, "
                "ASSAY_TYPE AS ASSAY_TYPE, "
                "TITER AS TITER "
                f"FROM {managed}"
            )
            print(f"SEMVIEW_DIAG provisioned single-table VIEW {fqn}{_VIEW_NAME}")
        finally:
            cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    data_product.provision()
