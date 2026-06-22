"""spec.py for the pharma-rx-demo (DP_RX) semantic-layer data product.

Exposes three MCP tools (list_models, describe_model, run_semantic_query) over a
governed semantic layer for the ``dispenses`` grain, served via an RPC output
port. Part of the fresh pharma mesh (MESH_DESIGN.md).

Deploy pattern: SELF-SEED (like ``deployable-dp/`` — NOT facade). The base
``DISPENSES`` table, the ``PHARMA_RX_MARKER`` table, and the single-table
``DISPENSES_SEMANTIC`` view are all seeded by the ``.transform(...)`` into this
DP's OWN Snowflake schema. The nxd validator HARD-REJECTS ``.transform()`` +
``as_view()`` together, and the rpc-tool sibling
bundling (``**/*.py`` glob) only fires when a transform exists — so
self-seed is the ONLY shape that both bundles ``registry.py`` / ``tools.py`` AND
validates.

The four non-negotiable wiring constraints (template README):
  1. code() cannot extract closures → module-level list_models/describe_model/
     run_semantic_query in tools.py; build_semantic_tools(REGISTRY) reused ONLY
     for each tool's request/response model + description.
  2. The registry sibling is bundled only if the DP declares a .transform(...).
  3. ALL modules flat at the DP root; import flat (`from registry import REGISTRY`).
  4. Base tables are SELF-SEEDED by the transform (CREATE + INSERT into this DP's
     own schema); the single-table semantic view references ONLY this DP's own
     table — never a cross-DP crosswalk.
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
from models import dispenses_model

INFRA_PROFILE = "ecommerce-demo"
SNOWFLAKE_SERVICE = "nxd-snowflake"

# Build semantic tools ONLY to obtain request/response models + descriptions.
# The actual callables are the module-level functions from tools.py which the
# spec builder can locate via AST (closures from build_semantic_tools cannot be).
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

# Storage output port named "snowflake" — its name is the transform's parameter
# name, and it supplies the Snowflake connection both the transform (to seed the
# tables + view) and run_semantic_query (to read it) use. Plain storage(...) with
# NO as_view — the transform self-seeds (template / self-seed pattern).
_storage = (
    data_product_output()
    # Promise the REAL dispenses model (not a marker) so the discover UI surfaces
    # its attributes + glossary links + cross-DP SEMANTIC RELATIONSHIP. The
    # transform seeds the matching DISPENSES table.
    .promise(dispenses_model)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"),
    )
)

spec = (
    data_product(
        name="pharma-rx-demo",
        domain="pharma",
        description=(
            "Semantic-layer data product over pharmacy dispense data (DP_RX). "
            "Exposes governed metrics (dispense_count, units_dispensed) and "
            "dimensions (dispense_channel, prescriber_npi[PII]) at the dispense "
            "grain via MCP so agents answer natural-language questions without "
            "raw SQL. Joins N:1 to site_subjects and products across the mesh."
        ),
        version="0.9.1-dev",
        infra_profile=INFRA_PROFILE,
    )
    # REAL MESH WIRING: declare the upstream DPs this one consumes. These inputs
    # establish the real upstream→downstream dependency in the mesh and must be
    # declared BEFORE the .transform(...).
    .input(
        "pharma-sites-demo",
        data_product_input()
        .source("https://nxd.nxd.local/data-product/pharma/pharma-sites-demo#/output/port/snowflake")
        .environment("demo"),
    )
    .input(
        "pharma-product-demo",
        data_product_input()
        .source("https://nxd.nxd.local/data-product/pharma/pharma-product-demo#/output/port/snowflake")
        .environment("demo"),
    )
    # TRANSFORM-SEED: the transform seeds the DISPENSES table + marker + the
    # single-table semantic view in one pass, and bundles registry.py/tools.py
    # (the **/*.py glob runs on the transform path). Output-port promise
    # verification does NOT run before the transform, so this deploys green in one
    # launch. .startup_timeout(600) covers cold-boot contention at mesh launch.
    .transform(
        code(transform).compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute").startup_timeout(600)
    )
    .output(_storage)
    .output(_rpc)
    # Glossary links — terms this DP relates to (pharma-glossary-demo term ids).
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/dispense")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/subject")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/product")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/prescriber")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/site")
)
