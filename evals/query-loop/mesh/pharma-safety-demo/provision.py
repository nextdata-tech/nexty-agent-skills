"""Pre-provision hook for pharma-safety-demo — the FAR ADVERSE-EVENTS FACT of the mesh.

Provisions the serving objects in this DP's Snowflake schema BEFORE the
transform runs:

  1. ``CREATE TABLE IF NOT EXISTS`` the promised ``adverse_events`` model's
     managed table (structure only — the transform fills the rows).
  2. ``CREATE OR REPLACE VIEW ADVERSE_EVENTS_SEMANTIC`` — the single-table
     semantic view the run_semantic_query compiler reads. Binding it here is safe
     because step 1 created the table object (the view references the object, not
     rows).

Lifecycle ordering: the ``@on_provision`` hook runs in Phase A, before the
transform. The output-port promise (rows present in the managed table) is
verified AFTER the transform, so provisioning structure here + seeding rows in
the transform satisfies the promise in one launch.

CRITICAL (MESH_DESIGN.md, the pharma-labs-demo break): this DP's registry has a
cross-DP MANY_TO_ONE join to `site_subjects` (owned by DP_SITES, lives in
ANOTHER schema). We therefore hand-author a SINGLE-TABLE view over
`adverse_events` only — we MUST NOT emit a JOIN to the crosswalk table in the
other DP's schema, or `CREATE VIEW` binds a missing object and the DP fails. The
cross-DP join resolves at QUERY time via the live mesh, not at view creation.

The hook receives the ``snowflake`` storage output port by parameter name (the
``ProvisionOutputPortArgumentProvider`` injects it as a typed ``Snowflake``
handle — same API the transform uses).
"""

from nxd import data_product
from nxd.data_product.context import Snowflake

_VIEW_NAME = "ADVERSE_EVENTS_SEMANTIC"  # = SnowflakeDialect.default_view_name(REGISTRY) for model `adverse_events`


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
            # 1) Create the PROMISED `adverse_events` model's managed table
            # (structure only). full_table_name("adverse_events") is the exact
            # table the storage driver verifies the promise against; the transform
            # writes the rows.
            managed = snowflake.full_table_name("adverse_events")
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {managed} "
                "(AE_ID NUMBER, SUBJECT_ID NUMBER, AE_TERM VARCHAR, IS_SERIOUS BOOLEAN)"
            )
            print(f"SEMVIEW_DIAG provisioned TABLE {managed}")

            # 2) Hand-authored SINGLE-TABLE semantic view over ADVERSE_EVENTS ONLY.
            #    We deliberately DO NOT emit the cross-DP JOIN to site_subjects
            #    (another DP's schema) — that would bind a missing object and fail
            #    CREATE VIEW. The cross-DP join resolves at query time via the mesh.
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS "
                "SELECT AE_ID AS AE_ID, "
                "SUBJECT_ID AS SUBJECT_ID, "
                "AE_TERM AS AE_TERM, "
                "IS_SERIOUS AS IS_SERIOUS "
                f"FROM {managed}"
            )
            print(f"SEMVIEW_DIAG provisioned single-table VIEW {fqn}{_VIEW_NAME}")
        finally:
            cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    data_product.provision()
