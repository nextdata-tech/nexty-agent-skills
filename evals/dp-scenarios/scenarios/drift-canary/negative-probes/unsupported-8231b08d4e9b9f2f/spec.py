"""One-construct negative probe for the documented semantic_tools boundary."""

from nxd.spec import data_product, data_product_output, field, primary_key, script, semantic_model, storage
from nxd.spec.data_types import number


_duckdb = "/infra-profile/desktop-local#/services/duckdb"
_compute = "/infra-profile/desktop-local#/services/python-compute"

_model = semantic_model("canary").schema({"id": field(number(), primary_key())})

spec = (
    data_product(
        name="unsupported-semantic-tools-8231b08d4e9b9f2f",
        domain="desktop.local",
        version="0.0.1",
        infra_profile="desktop-local",
    )
    .semantic_tools(service=_compute, backend="desktop")
    .transform(script("transform/main.py").compute(_compute))
    .output(data_product_output().promise(_model).port("duckdb", storage(_duckdb)))
)
