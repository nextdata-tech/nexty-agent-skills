"""crm-pipeline: a desktop data product authored entirely in Python. The
supervisor compiles this to the kernel definition YAML at create time."""

from nxd.spec import custom, data_product, data_product_output, script, storage

from models import deals, deals_metrics, nxd_decisions, nxd_decisions_metrics

_api = "/infra-profile/desktop-local#/services/api-source"
_compute = "/infra-profile/desktop-local#/services/python-compute"
_duckdb = "/infra-profile/desktop-local#/services/duckdb"

_output = (
    data_product_output()
    .promise(deals)
    .promise(
        custom("current-deals-non-deleted")
        .description("Every output row is a current (non-deleted) deal.")
        .model(deals)
        .verify(script("contracts/promises/current-deals-non-deleted.py").compute(_compute))
    )
    .promise(
        custom("current-deals-no-owner-pii")
        .description(
            "No output row, and no other stored surface of this product, "
            "includes owner name or owner email."
        )
        .model(deals)
        .verify(script("contracts/promises/current-deals-no-owner-pii.py").compute(_compute))
    )
    .promise(
        custom("current-deals-no-ranking")
        .description("No row or field in this output represents a priority or attention ranking.")
        .model(deals)
        .verify(script("contracts/promises/current-deals-no-ranking.py").compute(_compute))
    )
    .model(deals_metrics)
    .promise(nxd_decisions)
    .model(nxd_decisions_metrics)
    .port("duckdb", storage(_duckdb))
)

spec = (
    data_product(
        name="crm_pipeline",
        domain="desktop.local",
        version="0.0.1",
        infra_profile="desktop-local",
    )
    .transform(script("transform/main.py").compute(_compute).secrets([_api]))
    .output(_output)
)
