"""spec.py for the DP_PRODUCT semantic-layer data product (self-seeded).

Three MCP tools (list_models, describe_model, run_semantic_query) over the
`products` dimension (grain product_id) — a FAR dimension in the pharma mesh,
reachable multi-hop only (dispenses -> products). This DP is a ONE-side target:
it has NO outgoing joins.

The tool implementations live in tools.py (a flat sibling of this spec.py) as
top-level, module-level functions that reference REGISTRY from registry.py (also
a flat sibling). The spec builder requires module-level functions so it can
extract their source via AST parsing; closures produced by build_semantic_tools()
are nested and cannot be located (wiring constraint #1). Modules are flat at the
DP root so the extracted tool scripts resolve `from registry import REGISTRY`
against the script directory (wiring constraint #3).

Deploy pattern: SELF-SEED (mirrors `deployable-dp/`). The transform creates +
seeds this DP's OWN `products` base table and provisions a single-table
`PRODUCTS_SEMANTIC` view over it, then writes the promised marker. The storage
output port is a PLAIN `storage(...)` (NO `as_view` facade — the nxd validator
hard-rejects `.transform()` + `as_view()` together). The `.transform(...)` is
also what makes the `**/*.py` glob bundle registry.py / tools.py into the image
so the extracted rpc tool scripts can import them at runtime (constraint #2).
"""

from nxd.spec import (
    code,
    data_product,
    data_product_output,
    data_product_rpc_output,
    rpc_function,
    rpc_server,
    storage,
)
from nxd.experimental.semantic import build_semantic_tools
from registry import REGISTRY
from tools import list_models, describe_model, run_semantic_query
from transform import transform
from models import provision_marker

INFRA_PROFILE = "ecommerce-demo"
SNOWFLAKE_SERVICE = "nxd-snowflake"

# Build semantic tools to obtain the request/response models (schema descriptors).
# We use the library's build_semantic_tools() only for the .request_model,
# .response_model, and .description fields; the actual callable is the
# module-level function from tools.py which the spec builder can locate.
_tools = build_semantic_tools(REGISTRY)
_tool_map = {t.name: t for t in _tools}

_rpc = data_product_rpc_output()

for _fn, _name in [
    (list_models, "list_models"),
    (describe_model, "describe_model"),
    (run_semantic_query, "run_semantic_query"),
]:
    _t = _tool_map[_name]
    _rpc = _rpc.function(
        rpc_function(code(_fn), _t.request_model, _t.response_model).description(
            _t.description
        )
    )

_rpc = _rpc.port(
    "mcp-api",
    rpc_server(f"/infra-profile/{INFRA_PROFILE}#/services/mcp-api-service-k8s")
    .enable_endpoints()
    .mcp_path("/mcp"),
)

# Storage output port named "snowflake" — its name is the transform's parameter
# name, and it supplies the Snowflake connection both the transform (to seed the
# table + provision the view) and run_semantic_query (to read it) use. Plain
# storage(...) — NO facade; the transform self-seeds the marker the port promises.
_storage = (
    data_product_output()
    .promise(provision_marker)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"),
    )
)

spec = (
    data_product(
        name="pharma-product-demo",
        domain="analytics",
        description=(
            "Semantic-layer data product over the pharma `products` dimension "
            "(grain product_id) — a far dimension reachable multi-hop only. "
            "Exposes governed metrics and dimensions via MCP so agents can "
            "answer natural-language questions without raw SQL."
        ),
        version="0.1.0",
        infra_profile=INFRA_PROFILE,
    )
    # The transform self-seeds the `products` table + the single-table semantic
    # view AND makes the `**/*.py` glob bundle registry.py / tools.py into the
    # image so the extracted rpc tool scripts can import them at runtime.
    .transform(
        code(transform).compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute")
    )
    .output(_storage)
    .output(_rpc)
)
