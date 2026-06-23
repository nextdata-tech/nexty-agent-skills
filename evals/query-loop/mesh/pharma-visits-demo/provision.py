"""Pre-provision hook for pharma-visits-demo — fact #1 (clinical visits) of the mesh.

Provisions the serving objects in this DP's Snowflake schema BEFORE the
transform runs:

  1. ``CREATE TABLE IF NOT EXISTS`` the promised ``visits`` model's managed
     table (structure only — the transform fills the rows).
  2. ``CREATE OR REPLACE VIEW VISITS_SEMANTIC`` — the single-table semantic
     view the run_semantic_query compiler reads. Binding it here is safe because
     step 1 created the table object (the view references the object, not rows).

CRITICAL — cross-DP view-DDL ban: this DP's registry declares a MANY_TO_ONE
join from `visits` to `site_subjects` (a crosswalk hub OWNED by DP_SITES, in a
DIFFERENT Snowflake schema). The compiler's view DDL would emit a
`JOIN site_subjects` that binds an object not present in this schema. So the
single-table view is hand-authored over this DP's OWN `visits` table ONLY;
cross-DP joins resolve at QUERY time.

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

_VIEW_NAME = "VISITS_SEMANTIC"  # = SnowflakeDialect.default_view_name(REGISTRY) for model `visits`


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
            # 1) Create the PROMISED `visits` model's managed table (structure
            # only). full_table_name("visits") is the exact table the storage
            # driver verifies the promise against; the transform writes the rows.
            managed = snowflake.full_table_name("visits")
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {managed} "
                "(VISIT_ID NUMBER, SUBJECT_ID NUMBER, VISIT_TYPE VARCHAR, DURATION_MIN FLOAT)"
            )
            print(f"SEMVIEW_DIAG provisioned TABLE {managed}")

            # 2) Single-table semantic view over THIS DP's own `visits` table
            # ONLY. Deliberately NOT the compiler's view DDL — the registry's
            # cross-DP join to site_subjects would otherwise emit a JOIN into a
            # missing object.
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS "
                "SELECT VISIT_ID AS VISIT_ID, "
                "SUBJECT_ID AS SUBJECT_ID, "
                "VISIT_TYPE AS VISIT_TYPE, "
                "DURATION_MIN AS DURATION_MIN "
                f"FROM {managed}"
            )
            print(f"SEMVIEW_DIAG provisioned single-table VIEW {fqn}{_VIEW_NAME}")
        finally:
            cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    data_product.provision()
