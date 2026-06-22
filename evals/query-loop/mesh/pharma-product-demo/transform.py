"""Transform for the DP_PRODUCT semantic-layer data product (self-seeded).

Three jobs, all in this DP's OWN Snowflake schema:

1.  Seed this DP's OWN `products` base table (CREATE TABLE + INSERT) — the
    dimension the semantic layer reads. Self-contained: no dependency on any
    other DP's schema or pre-existing data.
2.  Provision a SINGLE-TABLE ``PRODUCTS_SEMANTIC`` view over that ONE table.
    Hand-authored — we do NOT call the compiler's
    ``native_semantic_view_ddl`` / ``plain_view_ddl``. `products` is a far
    dimension / ONE-side target with no outgoing joins, so a single-table
    projection is correct; hand-authoring also guarantees the view never binds
    a crosswalk/join table in another DP's schema (the pharma-labs-demo break).
3.  Write a one-row marker table (``pharma_product_marker``) — the single
    promised output model — so the storage port's produce-verification passes.

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
    view_name = SnowflakeDialect.default_view_name(REGISTRY)

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
            # 1) Seed this DP's OWN `products` base table.
            # Create UNQUOTED so Snowflake folds to upper-case — the hand-authored
            # view references the table name unquoted too (`FROM products`), so
            # both resolve to the same upper-cased object.
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

            # 2) Hand-author the SINGLE-TABLE semantic view over the seeded table.
            # References ONLY this DP's own `products` table — no JOIN, no
            # cross-DP crosswalk object. `products` is a leaf / ONE-side target.
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{view_name} AS\n"
                "SELECT\n"
                "    PRODUCT_ID,\n"
                "    PRODUCT_NAME,\n"
                "    MODALITY\n"
                f"FROM {fqn}products"
            )
            print(f"SEMVIEW_DIAG single-table OK provisioned VIEW {fqn}{view_name}")

            # 3) Marker (the promised output model).
            managed = snowflake.full_table_name("pharma_product_marker")
            marker_bare = managed.split(".")[-1].strip('"')
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": view_name}]),
                marker_bare,
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG marker written to {managed}")
        finally:
            cur.close()
    finally:
        conn.close()
