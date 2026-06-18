# ruff: noqa: F403, F405
from nxd_spec import *

spec = (
    data_product(
        name="session-rollups",
        domain="Web Analytics",
        description="Aggregates raw clickstream events into per-session rollups for downstream analytics.",
        version="0.3.0-dev",
        infra_profile="analytics-demo",
    )
    .environment("demo")
    .input(
        "events-api",
        source_aligned_input()
        .source("https://example.com/infra-profile/analytics-demo#/services/events-api")
        .expectation(events_model),
    )
    .output(
        data_product_output()
        .model(sessions_model)
        .promise(sessions_model)
        .port(
            "warehouse",
            storage("https://example.com/infra-profile/analytics-demo#/services/warehouse")
            .config(warehouse_config().target_table("SESSION_ROLLUPS", sessions_model)),
        )
    )
    .transform(
        script("transform.py")
        .compute("https://example.com/infra-profile/analytics-demo#/services/k8s-compute")
        .config(
            {
                "memory": "2Gi",
                "cpu": "1000m",
                "startup_timeout_secs": 600,
            }
        )
    )
    .control("owner", owner().user("hello@example.com"))
)
