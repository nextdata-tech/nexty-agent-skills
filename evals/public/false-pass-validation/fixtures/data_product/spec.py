# ruff: noqa: F403, F405
from nxd_spec import *

spec = (
    data_product(
        name="store-inventory",
        domain="Retail",
        description="Daily store inventory availability rollup derived from POS snapshots.",
        version="0.2.0-dev",
        infra_profile="retail-demo",
    )
    .environment("demo")
    .input(
        "pos-snapshots",
        source_aligned_input()
        .source("https://example.com/infra-profile/retail-demo#/services/pos-export")
        .expectation(inventory_snapshot_model),
    )
    .output(
        data_product_output()
        .model(availability_model)
        .promise(availability_model)
        .port(
            "warehouse",
            storage("https://example.com/infra-profile/retail-demo#/services/warehouse")
            .config(databricks_config().target_table("STORE_AVAILABILITY", availability_model)),
        )
    )
    .transform(script("transform.py"))
    .control("owner", owner().user("hello@example.com"))
    .control("steward", data_product_access().user("hello@example.com"))
)
