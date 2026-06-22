"""spec.py for the pharma-labs (DP_LABS) semantic-layer data product.

Fact #2 of the fresh pharma mesh (MESH_DESIGN.md). Models `assays`
(grain assay_id) — MANY assays per subject — exposing the confusable
titer_sum / titer_avg metric pair and an assay_type dimension. In the
registry it joins MANY_TO_ONE to the crosswalk hub `site_subjects` via
subject_id; that join resolves at QUERY time across the live mesh, NOT at
view-creation time (the view this DP provisions is single-table).

Three MCP tools (list_models, describe_model, run_semantic_query) are served
over an RPC output port. The tool implementations live in tools.py (a flat
sibling) as module-level functions referencing REGISTRY from registry.py (also
a flat sibling) — the spec builder extracts their source via AST, so they must
be module-level (not closures from build_semantic_tools), and flat (so the
extracted scripts can `from registry import REGISTRY` against the script dir).

SELF-SEED deploy pattern (MESH_DESIGN.md): the transform seeds this DP's OWN
base table (`ASSAYS`) and provisions the single-table `ASSAYS_SEMANTIC` view,
and the storage output port is a PLAIN storage(...) — no as_view facade. The
nxd validator hard-rejects `.transform()` + `as_view()` together, and the
rpc-tool sibling bundling (`**/*.py` glob) only fires when a transform exists,
so the self-seed path is the only one that both bundles siblings AND validates.
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
from tools import list_models, describe_model, run_semantic_query
from transform import transform
from models import assays_model

INFRA_PROFILE = "ecommerce-demo"
SNOWFLAKE_SERVICE = "nxd-snowflake"

# Build semantic tools ONLY for the request/response models + descriptions; the
# actual callables are the module-level functions from tools.py.
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

# Storage output port "snowflake" — PLAIN storage (NO as_view). Its name is the
# transform's parameter name and it supplies the Snowflake connection both the
# transform (to self-seed + provision the view) and run_semantic_query (to read
# it) use. Promise the REAL assays model (not a marker) so the discover UI
# surfaces its attributes + glossary links + the cross-DP SEMANTIC RELATIONSHIP.
_storage = (
    data_product_output()
    .promise(assays_model)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"),
    )
)

spec = (
    data_product(
        name="pharma-labs-demo",
        domain="pharma",
        description=(
            "Semantic-layer data product over lab assays (grain assay_id). "
            "Exposes the governed titer_sum / titer_avg metric pair and an "
            "assay_type dimension via MCP, joined many-to-one to the "
            "site_subjects crosswalk, so agents can answer natural-language "
            "questions without raw SQL."
        ),
        version="0.9.1-dev",
        infra_profile=INFRA_PROFILE,
    )
    # REAL MESH WIRING: DP_LABS consumes the upstream crosswalk DP_SITES. This
    # declares the genuine upstream→downstream dependency; the cross-DP join to
    # the subject spine resolves through site_subjects at query time across the
    # live mesh. Placed BEFORE .transform(...).
    .input(
        "pharma-sites-demo",
        data_product_input()
        .source(
            "https://nxd.nxd.local/data-product/pharma/pharma-sites-demo#/output/port/snowflake"
        )
        .environment("demo"),
    )
    # TRANSFORM-SEED: the transform seeds the ASSAYS table + marker + the
    # single-table semantic view in one pass, and bundles registry.py/tools.py
    # (the **/*.py glob runs on the transform path). Output-port promise
    # verification does NOT block a transform-seed, so this deploys green in one
    # launch. .startup_timeout(600) covers cold-boot contention at mesh launch.
    .transform(
        code(transform).compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute").startup_timeout(600)
    )
    .output(_storage)
    .output(_rpc)
    # GLOSSARY LINKS — relate this DP to the canonical pharma-glossary-demo terms
    # it touches. Term ids match glossary.yaml keys exactly.
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/assay")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/titer")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/subject")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/site")
)
