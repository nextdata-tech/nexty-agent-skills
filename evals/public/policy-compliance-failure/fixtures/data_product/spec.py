# ruff: noqa: F403, F405
from nxd_spec import *

spec = (
    data_product(
        name="customer-orders-curated",
        domain="Commerce",
        description="Curated, deduplicated customer orders published to Snowflake for downstream analytics.",
        version="0.3.0-dev",
        infra_profile="commerce-demo",
    )
    .environment("demo")
    .input(
        "orders-source",
        source_aligned_input()
        .source("https://example.com/infra-profile/commerce-demo#/services/orders-api")
        .expectation(orders_raw_model)
        .expectation(
            quality(soda, "contracts/orders_input_soda_checks.yml")
            .name("OrdersInputSodaCheck")
            .description("Soda checks on the raw orders source before transform")
            .model(orders_raw_model)
        )
        .config(s3_config(SupportedFormat.PARQUET).target_file("orders/raw/orders.parquet", orders_raw_model)),
    )
    .output(
        data_product_output()
        .model(orders_curated_model)
        .promise(orders_curated_model)
        .port(
            "snowflake",
            storage("https://example.com/infra-profile/commerce-demo#/services/nxd-snowflake")
            .config(snowflake_config("CURATED").target_table("ORDERS_CURATED", orders_curated_model)),
        )
    )
    .transform(script("transform.py"))
    .control("steward", data_product_access().user("hello@example.com"))
    .control("owner", owner().user("hello@example.com"))
)
