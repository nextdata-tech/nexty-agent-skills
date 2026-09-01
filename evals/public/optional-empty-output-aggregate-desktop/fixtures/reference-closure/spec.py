"""Python-only synthetic mapper aggregate desktop closure."""

from models import order_metrics, orders, reviews
from nxd.spec import data_product, data_product_output, script, storage


_csv = "/infra-profile/desktop-local#/services/csv-source"
_compute = "/infra-profile/desktop-local#/services/python-compute"
_duckdb = "/infra-profile/desktop-local#/services/duckdb"

_output = (
    data_product_output()
    .promise(orders)
    .model(reviews)
    .model(order_metrics)
    .port("duckdb", storage(_duckdb))
)

spec = (
    data_product(
        name="mapper-aggregate-e2e",
        description="Synthetic mapper product with an aggregate-only surface.",
        domain="desktop.local",
        version="0.0.1",
        infra_profile="desktop-local",
    )
    .transform(script("transform/main.py").compute(_compute).secrets([_csv]))
    .output(_output)
)
