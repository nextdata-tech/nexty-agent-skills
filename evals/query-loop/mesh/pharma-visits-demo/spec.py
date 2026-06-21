"""spec.py for the pharma-visits (DP_VISITS) semantic-layer data product.

Three MCP tools (list_models, describe_model, run_semantic_query) are exposed
over the self-seeded `visits` Snowflake dataset via an RPC output port.

The tool implementations live in tools.py (a flat sibling of this spec.py) as
top-level, module-level functions that reference REGISTRY from registry.py
(also a flat sibling). The spec builder requires module-level functions so it
can extract their source via AST parsing; closures produced by
build_semantic_tools() are nested and cannot be located by the parser
(constraint #1). The modules are kept flat at the DP root (constraint #3) so the
extracted tool scripts can resolve `from registry import REGISTRY` against the
script directory — the only path guaranteed on sys.path in the RPC subprocess.

SELF-SEED deploy pattern (constraint #4): the `.transform(...)` SEEDS this DP's
OWN base table and provisions a single-table semantic view at run time, then
writes the promised marker. The storage output port is a plain `storage(...)`
with NO `as_view` — the nxd validator HARD-REJECTS `as_view()` + `.transform()`
together, and the rpc-tool sibling bundling (`**/*.py` glob) REQUIRES a
transform. Self-seed is the only deployable shape.
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
# tables + provision the view) and run_semantic_query (to read it) use. Plain
# storage(...) — NO as_view (self-seed pattern).
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
        name="pharma-visits-demo",
        domain="analytics",
        description=(
            "Semantic-layer data product over clinical visits (one row per "
            "visit, MANY visits per subject). Exposes governed metrics "
            "(visit_count, visit_duration_min) and the visit_type dimension via "
            "MCP, joined MANY_TO_ONE through site_subjects into the subject "
            "spine, so agents answer natural-language questions without raw SQL."
        ),
        version="0.1.0",
        infra_profile=INFRA_PROFILE,
    )
    # The transform self-seeds this DP's OWN base table + single-table semantic
    # view AND is what makes the **/*.py glob bundle registry.py / tools.py into
    # the image so the extracted rpc tool scripts can import them at runtime.
    .transform(
        code(transform).compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute")
    )
    .output(_storage)
    .output(_rpc)
)
