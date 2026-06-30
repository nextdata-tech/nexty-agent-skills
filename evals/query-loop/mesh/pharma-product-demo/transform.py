"""Transform for pharma-product-demo — the `products` FAR dimension (self-seeded).

Two jobs, all in this DP's OWN Snowflake schema:

1.  Seed the small base table (``products``) the semantic MCP tools read.
    Self-contained: no dependency on any other DP's schema or pre-existing data.
    CREATE OR REPLACE so re-runs are idempotent.
2.  Write a one-row marker table (``products_smoke_marker``) — the primary
    promised output model — so the storage port's produce-verification passes.

The semantic view provisioning from the old registry.py/provision.py-based
implementation is removed. The auto-generated ``run_semantic_query`` (from
``nxd.experimental.semantic.entrypoints``) compiles governed SQL against the
base table directly, reading the kernel-delivered
``<root>/.nxd/semantic/<model>.json`` payloads. No pre-provisioned view is
required.
"""

from nxd.data_product.context import Snowflake


def transform(snowflake: Snowflake) -> None:
    import pandas as pd
    from snowflake.connector.pandas_tools import write_pandas

    from snowflake import connector

    if snowflake is None or not snowflake.schema:
        print("SEMVIEW_DIAG skipped — no Snowflake schema in context")
        return

    fqn = (
        f"{snowflake.database}.{snowflake.schema}."
        if snowflake.database
        else f"{snowflake.schema}."
    )

    products = pd.DataFrame(
        [
            {"PRODUCT_ID": 1, "PRODUCT_NAME": "Humira", "MODALITY": "antibody"},
            {"PRODUCT_ID": 2, "PRODUCT_NAME": "Lipitor", "MODALITY": "small_molecule"},
            {"PRODUCT_ID": 3, "PRODUCT_NAME": "Comirnaty", "MODALITY": "vaccine"},
            {"PRODUCT_ID": 4, "PRODUCT_NAME": "Keytruda", "MODALITY": "antibody"},
            {"PRODUCT_ID": 5, "PRODUCT_NAME": "Metformin", "MODALITY": "small_molecule"},
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
            # Seed the products base table (name matches the spec model).
            # Create UNQUOTED so Snowflake folds to upper-case — the compiler's
            # base-table SQL references the table name unquoted too, so both
            # resolve to the same upper-cased object.
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}products "
                "(PRODUCT_ID NUMBER, PRODUCT_NAME VARCHAR, MODALITY VARCHAR)"
            )
            write_pandas(
                conn,
                products,
                "PRODUCTS",
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG seeded {fqn}products rows={len(products)}")

            # Write the marker row (promised output model).
            managed = snowflake.full_table_name("products_smoke_marker")
            marker_bare = managed.split(".")[-1].strip('"')
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": "n/a"}]),
                marker_bare,
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG marker written to {managed}")

        finally:
            cur.close()
    finally:
        conn.close()
