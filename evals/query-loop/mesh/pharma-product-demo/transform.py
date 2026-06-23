"""Transform for pharma-product-demo — the `products` FAR dimension.

Seeds the ROWS of the promised `products` model's managed table. The table
STRUCTURE and the single-table `PRODUCTS_SEMANTIC` view are created earlier by
the `@on_provision` hook (provision.py), which runs in Phase A before this
transform. This transform only writes the data the output-port promise verifies.

The `.transform()` is also what bundles the sibling `registry.py` / `tools.py` /
`provision.py` modules into the image (the `**/*.py` glob runs on the
transform/compute path).
"""

import pandas as pd
from nxd.data_product.context import Snowflake


def transform(snowflake: Snowflake) -> None:
    from snowflake import connector
    from snowflake.connector.pandas_tools import write_pandas

    if snowflake is None or not snowflake.schema:
        print("SEMVIEW_DIAG transform skipped — no Snowflake schema in context")
        return

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
        managed = snowflake.full_table_name("products")
        # Truncate-and-load so repeated runs stay deterministic (the provision
        # hook created the table with CREATE TABLE IF NOT EXISTS, so it may
        # already hold rows from a prior run).
        cur = conn.cursor()
        try:
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
        finally:
            cur.close()
        write_pandas(conn, products, managed.split(".")[-1].strip('"'),
                     database=snowflake.database, schema=snowflake.schema)
        print(f"SEMVIEW_DIAG seeded {managed} rows={len(products)}")
    finally:
        conn.close()
