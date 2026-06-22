"""spec.py for DP_SITES (pharma-sites-demo).

Exposes three MCP tools (list_models, describe_model, run_semantic_query) over
the DP_SITES semantic layer — the MANY_TO_MANY crosswalk hub (`site_subjects`)
plus the `sites` dimension — via an RPC output port.

Wiring constraints (non-negotiable, from the deployable-dp template README):

1. code() cannot extract closures → the tool callables are module-level
   functions in tools.py (a flat sibling) that delegate to the library;
   build_semantic_tools(REGISTRY) is used ONLY for each tool's request/response
   model + description.
2. The registry sibling is bundled only because this DP declares a .transform —
   the **/*.py glob on the transform/compute path bundles registry.py / tools.py.
3. All modules are FLAT at the DP root; imports are flat (from registry import
   REGISTRY) so the rpc subprocess (only its own dir on sys.path) resolves them.
4. Base tables are SELF-SEEDED by the post-verify transform (like the
   deployable-dp template), NOT via a facade. The nxd validator HARD-REJECTS
   `.transform()` + `storage().as_view(...)` together,
   and the rpc-tool sibling bundling (`**/*.py` glob) only fires when a transform
   exists — so the self-seed path is the ONLY one that both bundles registry.py /
   tools.py AND validates. The storage output port is a PLAIN storage(...) with
   NO as_view.
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
# base tables + provision the semantic view) and run_semantic_query (to read it)
# use. PLAIN storage(...) — NO as_view (self-seed pattern, mirrors the template).
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
        name="pharma-sites-demo",
        domain="analytics",
        description=(
            "DP_SITES — the MANY_TO_MANY crosswalk hub of the pharma mesh. "
            "Models the site_subjects crosswalk (grain site_id, subject_id) "
            "joining the subject spine to the sites dimension, plus the sites "
            "dimension itself. Exposes governed metrics and dimensions via MCP "
            "so agents can answer natural-language questions without raw SQL."
        ),
        version="0.1.0",
        infra_profile=INFRA_PROFILE,
    )
    # The transform provisions the semantic view the MCP tools query AND is what
    # makes the **/*.py glob bundle registry.py / tools.py into the image so the
    # extracted rpc tool scripts can import them at runtime.
    .transform(
        code(transform).compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute")
    )
    .output(_storage)
    .output(_rpc)
)
