# ruff: noqa: F403, F405
from nxd_spec import *

spec = (
    data_product(
        name="amazon-sales",
        description="Per-order Amazon sales records (ASIN, ship date) lifted from "
        "the daff-s3 check-state CSV export into the daff Snowflake "
        "CHECK_POSTFIX_STAGING schema. Near-passthrough source-aligned "
        "input/output — the only transformation is normalising the CSV "
        "header `date-shipped` to `date_shipped`.",
        domain="sales",
        version="1.0.0-dev",
        infra_profile="daff-demo-infra-profile",
    )
    .environment("demo")
    .input(
        "s3-source",
        source_aligned_input()
        .source("https://app.demo.nextopia.dev/infra-profile/daff-demo-infra-profile#/services/daff-s3")
        .model(amazon_sales)
        .expectation(amazon_sales)
        .config(
            s3_config(SupportedFormat.CSV).target_file(
                "check-state/demo/amazon-sales.csv", amazon_sales
            )
        ),
    )
    .output(
        data_product_output()
        .model(amazon_sales)
        .promise(amazon_sales)
        .port(
            "snowflake",
            storage("https://app.demo.nextopia.dev/infra-profile/daff-demo-infra-profile#/services/nxd-snowflake").config(
                snowflake_config("CHECK_POSTFIX_STAGING").target_table(
                    "AMAZON_SALES", amazon_sales
                )
            ),
        )
    )
    .transform(
        code(transform)
        .compute("https://app.demo.nextopia.dev/infra-profile/daff-demo-infra-profile#/services/k8s-compute")
        # TODO: confirm schedule cadence with owner; defaulting to daily.
        .when(scheduled("0 6 * * *"), startup=True)
    )
    # TODO: replace placeholder users with real owner / steward / access.
    .control("owner", owner().user("hello@nextdata.com"))
    .control("steward", data_product_access().user("hello@nextdata.com"))
    .control("data-product-access", data_product_access().user("hello@nextdata.com"))
)
