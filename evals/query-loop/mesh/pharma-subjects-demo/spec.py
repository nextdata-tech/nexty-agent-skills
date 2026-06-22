"""spec.py for pharma-subjects-demo — the SUBJECT SPINE of the fresh pharma mesh.

Three MCP tools (list_models, describe_model, run_semantic_query) over the
`subjects` semantic model in Snowflake, served via an RPC output port.

The four non-negotiable wiring constraints (deployable-dp README):
1. `code()` cannot extract closures — the tool callables are module-level defs
   in tools.py that delegate to the library; build_semantic_tools(REGISTRY) is
   used ONLY for each tool's request/response models + description.
2. The registry/tools siblings are bundled only because a `.transform(...)` is
   declared (the **/*.py glob runs on the transform/compute output path).
3. All modules are FLAT at the DP root; imports are flat (`from registry import
   REGISTRY`).
4. Base tables are SELF-SEEDED by the transform into this DP's own Snowflake
   schema (the template pattern — NOT the facade). The storage port is a plain
   `storage(...)` with NO `as_view` (the nxd validator HARD-REJECTS
   `.transform()` + `as_view()` together), and there is no `source_aligned_input`.
"""

from nxd.spec import (
    code,
    data_product,
    data_product_output,
    data_product_rpc_output,
    Predicate,
    rpc_function,
    rpc_server,
    storage,
)
from nxd.experimental.semantic import build_semantic_tools
from registry import REGISTRY
from tools import list_models, describe_model, run_semantic_query
from transform import transform
from models import subjects_model

INFRA_PROFILE = "ecommerce-demo"
SNOWFLAKE_SERVICE = "nxd-snowflake"

# Build semantic tools ONLY to obtain the request/response schema descriptors +
# descriptions; the actual callables are the module-level functions from tools.py
# (which the spec builder can locate via AST — closures cannot be located).
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
# base table + provision the view) and run_semantic_query (to read it) use.
# Plain storage(...) with NO as_view: the self-seed transform owns provisioning.
_storage = (
    data_product_output()
    # Promise the REAL subjects model (not a marker) so the discover UI surfaces
    # its attributes + glossary links. The transform seeds the matching SUBJECTS table.
    .promise(subjects_model)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"),
    )
)

spec = (
    data_product(
        name="pharma-subjects-demo",
        domain="pharma",
        description=(
            "Subject-spine semantic-layer data product for the fresh pharma mesh. "
            "Exposes the `subjects` model (grain SUBJECT_ID) — governed metric "
            "subject_count and dimensions subject_country + subject_mrn[PII] — via "
            "MCP so agents answer natural-language questions without raw SQL."
        ),
        version="0.9.1-dev",
        infra_profile=INFRA_PROFILE,
    )
    # TRANSFORM-SEED: the transform seeds the SUBJECTS table + marker + the
    # single-table semantic view in one pass, and bundles registry.py/tools.py
    # (the **/*.py glob runs on the transform path). Output-port promise
    # verification does NOT run before the transform (only input expectations do,
    # and this spine DP has no inputs), so this deploys green in one launch.
    # .startup_timeout(600) covers cold-boot contention when the mesh launches.
    .transform(
        code(transform).compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute").startup_timeout(600)
    )
    .output(_storage)
    .output(_rpc)
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/subject")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/subject_country")
)
