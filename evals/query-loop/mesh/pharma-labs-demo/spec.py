"""spec.py for the pharma-labs (DP_LABS) semantic-layer data product.

Fact #2 of the fresh pharma mesh (MESH_DESIGN.md). Models `assays`
(grain assay_id) — MANY assays per subject — exposing the confusable
titer_sum / titer_avg metric pair and an assay_type dimension. In the
semantic registry it joins MANY_TO_ONE to the crosswalk hub `site_subjects`
via subject_id; that join resolves at QUERY time across the live mesh, NOT at
view-creation time.

Four MCP tools (list_models, semantic_model, describe_model,
run_semantic_query) are auto-generated at pod boot via the .semantic_tools()
flag (NEX-710 / PR #6979). The kernel compiles per-field __nxd_semantic__ blobs
on each promised model's manifest attributes into typed SemanticRegistry
payloads, delivers them to ``<root>/.nxd/semantic/<model>.json`` at startup, and
the entrypoints module reads them back to build the four tool closures.

Manifest authoring
------------------
The Python spec author surface for __nxd_semantic__ field annotations
(NEX-704) is not yet merged. The annotations are injected via a private-field
stopgap in models.py:
  AttributeSpec._metadata["__nxd_semantic__"] = json.dumps(role)

Wiring
------
- assays_model + provision_marker promised on the storage port so their
  annotated attributes appear in the kernel's manifest (and thus in
  .nxd/semantic/*.json at pod boot).
- .semantic_tools() auto-wires 4 RPC tool functions + mcp-api port.
- The transform seeds the assays base table and writes the marker row.
"""

from nxd.spec import (
    Predicate,
    code,
    data_product,
    data_product_input,
    data_product_output,
    storage,
)
from transform import transform
from models import assays_model, provision_marker

INFRA_PROFILE = "ecommerce-demo"
SNOWFLAKE_SERVICE = "nxd-snowflake"

# Storage output port "snowflake" — PLAIN storage. Its name is the transform's
# parameter name and it supplies the Snowflake connection both the transform (to
# self-seed the base table + marker) and run_semantic_query (to read it) use.
# Promise the REAL assays model (not just a marker) so the discover UI surfaces
# its attributes + glossary links + the cross-DP SEMANTIC RELATIONSHIP.
_storage = (
    data_product_output()
    .promise(provision_marker)
    .promise(assays_model)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"),
    )
    .managed_access()
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
        version="1.0.0-dev",
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
    # TRANSFORM: seeds the assays base table + the marker row. No semantic-view
    # DDL needed — the auto-generated run_semantic_query compiles SQL against the
    # base table from the kernel-delivered .nxd/semantic/ payloads.
    # .startup_timeout(600) covers cold-boot contention when the mesh launches.
    .transform(
        code(transform).compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute").startup_timeout(600)
    )
    .output(_storage)
    # Deploy on the `demo` env so this fact's `.input(...).environment("demo")`
    # edges resolve against the demo-env upstreams. Whole mesh on one env.
    .environment("demo")
    # Auto-wire 4 governed MCP tools (list_models, semantic_model,
    # describe_model, run_semantic_query) reading kernel-delivered payloads.
    .semantic_tools(service="mcp-api-service-k8s")
    # GLOSSARY LINKS — relate this DP to the canonical pharma-glossary-demo terms
    # it touches. Term ids match glossary.yaml keys exactly.
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/assay")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/titer")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/subject")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/site")
)
