"""spec.py for the pharma-product-demo semantic-layer data product (self-seeded).

Four MCP tools (list_models, semantic_model, describe_model, run_semantic_query)
over the `products` dimension (grain product_id) — a FAR dimension in the pharma
mesh, reachable multi-hop only (dispenses -> products). This DP is a ONE-side
target: it has NO outgoing joins.

The tools are auto-generated at pod boot via the .semantic_tools() flag (NEX-710
/ PR #6979). The kernel compiles per-field __nxd_semantic__ blobs on each
promised model's manifest attributes into typed SemanticRegistry payloads,
delivers them to ``<root>/.nxd/semantic/<model>.json`` at startup, and the
entrypoints module reads them back to build the four tool closures.

Manifest authoring
------------------
The Python spec author surface for __nxd_semantic__ field annotations (NEX-704)
is not yet merged. The annotations are injected via a private-field stopgap in
models.py:
  AttributeSpec._metadata["__nxd_semantic__"] = json.dumps(role)

Wiring
------
- products promised on the storage port so its annotated attributes appear in
  the kernel's manifest (and thus in .nxd/semantic/*.json at pod boot).
- provision_marker is also promised (satisfies produce-verification).
- .semantic_tools() auto-wires 4 RPC tool functions + mcp-api port.
- The transform seeds the base table and writes the marker row.
"""

from nxd.spec import (
    Predicate,
    code,
    data_product,
    data_product_output,
    storage,
)
from transform import transform
from models import products_model, provision_marker

INFRA_PROFILE = "ecommerce-demo"
SNOWFLAKE_SERVICE = "nxd-snowflake"

# Storage output port named "snowflake" — its name is the transform's parameter
# name, and it supplies the Snowflake connection both the transform (to seed the
# table) and run_semantic_query (to read it) use. Plain storage(...) — NO facade;
# the transform self-seeds the promised products table.
_storage = (
    data_product_output()
    .promise(provision_marker)
    # Promise the REAL products model (not just a marker) so the discover UI
    # surfaces its attributes + glossary links. The transform seeds the matching
    # PRODUCTS table.
    .promise(products_model)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"),
    )
    .managed_access()
)

spec = (
    data_product(
        name="pharma-product-demo",
        domain="pharma",
        description=(
            "Semantic-layer data product over the pharma `products` dimension "
            "(grain product_id) — a far dimension reachable multi-hop only. "
            "Exposes governed metrics and dimensions via MCP so agents can "
            "answer natural-language questions without raw SQL."
        ),
        version="1.0.0-dev",
        infra_profile=INFRA_PROFILE,
    )
    # TRANSFORM: seeds the `products` base table and writes the
    # products_smoke_marker row. No semantic-view DDL needed — the auto-generated
    # run_semantic_query compiles SQL against the base table from the
    # kernel-delivered .nxd/semantic/ payloads. .startup_timeout(600) covers
    # cold-boot contention when the mesh launches.
    .transform(
        code(transform).compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute").startup_timeout(600)
    )
    .output(_storage)
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/product")
    # Auto-wire 4 governed MCP tools (list_models, semantic_model,
    # describe_model, run_semantic_query) reading kernel-delivered payloads.
    .semantic_tools(service="mcp-api-service-k8s")
)
