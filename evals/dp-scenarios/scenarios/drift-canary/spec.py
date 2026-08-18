"""Kitchen-sink Python closure for the documentation/runtime canary."""

from models import api_events, customers, db_rows, event_metrics, file_rows, optional_zero, orders
from nxd.spec import data_product, data_product_output, script, storage


_csv = "/infra-profile/desktop-local#/services/csv-source"
_file = "/infra-profile/desktop-local#/services/file-source"
_db = "/infra-profile/desktop-local#/services/db-source"
_api = "/infra-profile/desktop-local#/services/api-source"
_compute = "/infra-profile/desktop-local#/services/python-compute"
_duckdb = "/infra-profile/desktop-local#/services/duckdb"

_output = (
    data_product_output()
    .promise(orders)
    .promise(file_rows)
    .promise(db_rows)
    .promise(api_events)
    .promise(optional_zero)
    .model(customers)
    .model(event_metrics)
    .port("duckdb", storage(_duckdb))
)

spec = (
    data_product(
        name="skill-runtime-drift-canary",
        domain="desktop.local",
        version="0.0.1",
        infra_profile="desktop-local",
    )
    .transform(script("transform/main.py").compute(_compute).secrets([_csv, _file, _db, _api]))
    .output(_output)
)
