"""A desktop data product authored entirely in Python. The supervisor compiles
this to the kernel definition YAML at create time."""

from nxd.spec import data_product, data_product_output, script, storage

from models import events, event_metrics

_csv = "/infra-profile/desktop-local#/services/csv-source"
_compute = "/infra-profile/desktop-local#/services/python-compute"
_duckdb = "/infra-profile/desktop-local#/services/duckdb"

_output = (
    data_product_output()
    .promise(events)
    .model(event_metrics)
    .port("duckdb", storage(_duckdb))
)

spec = (
    data_product(
        name="storefront-events",
        domain="desktop.local",
        version="0.0.1",
        infra_profile="desktop-local",
    )
    .transform(script("transform/main.py").compute(_compute).secrets([_csv]))
    .output(_output)
)
