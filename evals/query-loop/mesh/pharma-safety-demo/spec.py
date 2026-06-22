"""spec.py for the pharma-safety (DP_SAFETY) semantic-layer data product.

The far adverse-events fact of the fresh pharma mesh (MESH_DESIGN.md). Models
`adverse_events` (grain ae_id) — MANY adverse events per subject — exposing the
ae_term dimension and the confusable ae_count / serious_ae_count metric pair
(serious_ae_count is a boolean CASE-sum over IS_SERIOUS, NOT a numeric SUM),
joined MANY_TO_ONE to the crosswalk hub `site_subjects` via subject_id (a
cross-DP join resolved at the mesh layer, NOT materialised in this DP's view).

Three MCP tools (list_models, describe_model, run_semantic_query) are served
over an RPC output port. The tool implementations live in tools.py (a flat
sibling) as module-level functions referencing REGISTRY from registry.py (also
a flat sibling) — the spec builder extracts their source via AST, so they must
be module-level (not closures from build_semantic_tools), and flat (so the
extracted scripts can `from registry import REGISTRY` against the script dir).

SELF-SEED deploy pattern (MESH_DESIGN.md): the storage output port is a PLAIN
`storage(...)` (NO `as_view` — the nxd validator hard-rejects facade `as_view` +
`.transform()` together). The `.transform()` self-seeds this DP's OWN base table
+ marker + single-table semantic view, AND is what makes the `**/*.py` glob
bundle registry.py / tools.py into the image so the extracted rpc tool scripts
can import them at runtime.
"""

from nxd.spec import (
    Predicate,
    code,
    data_product,
    data_product_input,
    data_product_output,
    data_product_rpc_output,
    rpc_function,
    rpc_server,
    storage,
)
from nxd.experimental.semantic import build_semantic_tools
from registry import REGISTRY
from tools import list_models, describe_model, run_semantic_query, semantic_model
from transform import transform
from models import adverse_events_model

INFRA_PROFILE = "ecommerce-demo"
SNOWFLAKE_SERVICE = "nxd-snowflake"

# Build semantic tools ONLY for the request/response models + descriptions; the
# actual callables are the module-level functions from tools.py.
_tools = build_semantic_tools(REGISTRY)
_tool_map = {t.name: t for t in _tools}

_rpc = data_product_rpc_output()

for _fn, _name in [
    (list_models, "list_models"),
    (semantic_model, "semantic_model"),
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

# Storage output port "snowflake" — PLAIN storage (NO as_view). Its name is the
# transform's parameter name and it supplies the Snowflake connection both the
# transform (to self-seed the tables + view) and run_semantic_query (to read
# them) use.
_storage = (
    data_product_output()
    # Promise the REAL adverse_events model (not a marker) so the discover UI
    # surfaces its attributes + glossary links + the cross-DP SUBJECT_ID
    # relationship. The transform seeds the matching ADVERSE_EVENTS table.
    .promise(adverse_events_model)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"),
    )
)

spec = (
    data_product(
        name="pharma-safety-demo",
        domain="pharma",
        description=(
            "Semantic-layer data product over adverse events (grain ae_id). "
            "Exposes the ae_term dimension and the governed ae_count / "
            "serious_ae_count metric pair (serious_ae_count is a boolean CASE-sum "
            "over IS_SERIOUS) via MCP, joined many-to-one to the site_subjects "
            "crosswalk, so agents can answer natural-language safety questions "
            "without raw SQL."
        ),
        version="0.9.1-dev",
        infra_profile=INFRA_PROFILE,
    )
    # REAL MESH WIRING — consume the upstream pharma-sites-demo crosswalk hub DP.
    # This declares the upstream→downstream dependency; the cross-DP join to
    # site_subjects (in registry.py) resolves at query time via the live mesh.
    .input(
        "pharma-sites-demo",
        data_product_input()
        .source(
            "https://nxd.nxd.local/data-product/pharma/pharma-sites-demo#/output/port/snowflake"
        )
        .environment("demo"),
    )
    # TRANSFORM-SEED: the transform seeds this DP's OWN adverse_events table +
    # marker + the single-table semantic view in one pass, and bundles
    # registry.py/tools.py (the **/*.py glob runs on the transform path).
    # .startup_timeout(600) covers cold-boot contention when the mesh launches.
    .transform(
        code(transform).compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute").startup_timeout(600)
    )
    .output(_storage)
    .output(_rpc)
    # GLOSSARY LINKS — relate this DP to the canonical mesh terms it touches.
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/adverse_event")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/subject")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/site")
)
