"""Pre-provision hook for pharma-sites-demo — the MANY_TO_MANY crosswalk HUB.

Provisions the serving objects in this DP's Snowflake schema BEFORE the
transform runs:

  1. ``CREATE TABLE IF NOT EXISTS`` this DP's OWN ``sites`` dimension table
     (structure only — the transform fills the rows). UNQUOTED so Snowflake
     folds the name to upper-case (SITES), matching the unquoted references in
     the view below.
  2. ``CREATE TABLE IF NOT EXISTS`` the promised ``site_subjects`` model's
     managed table (structure only — the transform fills the rows).
  3. ``CREATE OR REPLACE VIEW SITE_SUBJECTS_SEMANTIC`` — the single-table
     semantic view the run_semantic_query compiler reads. Binding it here is
     safe because steps 1-2 created the table objects (the view references the
     objects, not rows).

Lifecycle ordering: the ``@on_provision`` hook runs in Phase A, before the
transform. The output-port promise (rows present in the managed table) is
verified AFTER the transform, so provisioning structure here + seeding rows in
the transform satisfies the promise in one launch.

The hook receives the ``snowflake`` storage output port by parameter name (the
``ProvisionOutputPortArgumentProvider`` injects it as a typed ``Snowflake``
handle — same API the transform uses).

CRITICAL — the single-table view references ONLY this DP's own tables
(SITES / SITE_SUBJECTS). The registry declares a cross-DP MANY_TO_ONE join
(site_subjects -> subjects, owned by pharma-subjects-demo); a compiler-generated
view would emit a JOIN to a table in another DP's schema and fail CREATE VIEW at
deploy. The cross-DP subject join resolves at QUERY time via the live mesh.
"""

from nxd import data_product
from nxd.data_product.context import Snowflake

_VIEW_NAME = "SITE_SUBJECTS_SEMANTIC"  # = SnowflakeDialect.default_view_name(REGISTRY) for model `site_subjects`


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
            # 1) Create this DP's OWN site DIMENSION table (structure only;
            #    the transform writes the rows). UNQUOTED so Snowflake folds to
            #    upper-case, matching the unquoted references in the view below.
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {fqn}sites "
                "(SITE_ID NUMBER, SITE_REGION VARCHAR)"
            )
            print(f"SEMVIEW_DIAG provisioned TABLE {fqn}sites")

            # 2) Create the PROMISED `site_subjects` model's managed table
            #    (structure only). full_table_name("site_subjects") is the exact
            #    table the storage driver verifies the promise against; the
            #    transform writes the rows.
            managed = snowflake.full_table_name("site_subjects")
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {managed} "
                "(SITE_ID NUMBER, SUBJECT_ID NUMBER)"
            )
            print(f"SEMVIEW_DIAG provisioned TABLE {managed}")

            # 3) Hand-authored SINGLE-TABLE semantic view over THIS DP's own tables
            #    only. Do NOT use the compiler DDL helpers — the registry has a
            #    cross-DP join (site_subjects -> subjects, owned by
            #    pharma-subjects-demo) and they would emit a JOIN to a table in
            #    another DP's schema, failing CREATE VIEW at deploy. The crosswalk
            #    grain (SITE_ID, SUBJECT_ID) joined to its OWN site dimension is
            #    fully resolvable here; the cross-DP subject join resolves at query
            #    time via the live mesh.
            view_ddl = (
                f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS\n"
                f"SELECT\n"
                f"    ss.SITE_ID      AS SITE_ID,\n"
                f"    ss.SUBJECT_ID   AS SUBJECT_ID,\n"
                f"    s.SITE_REGION   AS SITE_REGION\n"
                f"FROM {managed} AS ss\n"
                f"LEFT JOIN {fqn}sites AS s\n"
                f"    ON ss.SITE_ID = s.SITE_ID"
            )
            cur.execute(view_ddl)
            print(
                f"SEMVIEW_DIAG single-table OK provisioned VIEW {fqn}{_VIEW_NAME} "
                f"(this DP's own SITES / SITE_SUBJECTS only)"
            )
        finally:
            cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    data_product.provision()
