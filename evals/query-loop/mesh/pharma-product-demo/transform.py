"""Transform for pharma-product-demo — TRANSFORM-SEED of the `products` dimension.

Seeds this DP's OWN base table (`PRODUCTS`) + the marker + the single-table
semantic view (`PRODUCTS_SEMANTIC`) in this DP's Snowflake schema, in ONE
transform pass. This is the proven `pharma-subjects-demo` pattern: output-port
promise verification does NOT run before the transform (only input *expectations*
verify early, and this far-dimension DP has no inputs), so a transform-seed
deploys green in one launch.

The `.transform()` is also what bundles the sibling `registry.py` / `tools.py`
modules into the image (the `**/*.py` glob runs on the transform/compute path).
"""

import pandas as pd
from nxd.data_product.context import Snowflake

_VIEW_NAME = "PRODUCTS_SEMANTIC"  # = SnowflakeDialect.default_view_name(REGISTRY) for model `products`


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
            # 0) Marker (the promised output model) so the storage port verifies.
            managed = snowflake.full_table_name("pharma_product_marker")
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": _VIEW_NAME}]),
                managed.split(".")[-1].strip('"'),
                database=snowflake.database,
                schema=snowflake.schema,
            )
            print(f"SEMVIEW_DIAG marker written to {managed}")

            # 1) Seed this DP's OWN `products` base table (unquoted -> upper).
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}products "
                "(PRODUCT_ID NUMBER, PRODUCT_NAME VARCHAR, MODALITY VARCHAR)"
            )
            write_pandas(conn, products, "PRODUCTS",
                         database=snowflake.database, schema=snowflake.schema)
            print(f"SEMVIEW_DIAG seeded {fqn}products rows={len(products)}")

            # 2) Hand-authored SINGLE-TABLE semantic view over PRODUCTS ONLY.
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS "
                "SELECT PRODUCT_ID AS PRODUCT_ID, "
                "PRODUCT_NAME AS PRODUCT_NAME, "
                "MODALITY AS MODALITY "
                f"FROM {fqn}products"
            )
            print(f"SEMVIEW_DIAG provisioned single-table VIEW {fqn}{_VIEW_NAME}")
        finally:
            cur.close()
    finally:
        conn.close()
