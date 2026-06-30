"""spec.py for the pharma-safety (DP_SAFETY) semantic-layer data product.

The far adverse-events fact of the fresh pharma mesh (MESH_DESIGN.md). Models
`adverse_events` (grain ae_id) — MANY adverse events per subject — exposing the
ae_term dimension and the confusable ae_count / serious_ae_count metric pair
(serious_ae_count is a boolean CASE-sum over IS_SERIOUS, NOT a numeric SUM),
joined MANY_TO_ONE to the crosswalk hub `site_subjects` via subject_id (a
cross-DP join resolved at the mesh layer, NOT materialised in this DP's view).

NEW `.semantic_tools()` pattern (NEX-710). Four MCP tools (list_models,
semantic_model, describe_model, run_semantic_query) are auto-generated at pod
boot via the .semantic_tools() flag. The kernel compiles per-field
__nxd_semantic__ blobs (declared in models.py) on each promised model's manifest
attributes into typed SemanticRegistry payloads, delivers them to
``<root>/.nxd/semantic/<model>.json`` at startup, and the entrypoints module
reads them back to build the four tool closures. No hand-authored registry.py /
tools.py / rpc loop / provision view.

Wiring
------
- adverse_events promised on the storage port so its annotated attributes appear
  in the kernel's manifest (and thus in .nxd/semantic/*.json at pod boot).
- provision_marker is also promised (satisfies produce-verification).
- .semantic_tools() auto-wires 4 RPC tool functions + mcp-api port.
- The transform self-seeds the base table and writes the marker row.
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
from models import adverse_events_model, provision_marker

INFRA_PROFILE = "ecommerce-demo"
SNOWFLAKE_SERVICE = "nxd-snowflake"

# Storage output port "snowflake" — PLAIN storage. Promises the marker model
# (produce-verification) and the REAL adverse_events model so its annotated
# attributes + glossary links + the cross-DP SUBJECT_ID relationship appear in
# the kernel-generated manifest. The kernel compiles __nxd_semantic__ blobs from
# those attributes and delivers a .nxd/semantic/<model>.json payload at boot.
_storage = (
    data_product_output()
    .promise(provision_marker)
    .promise(adverse_events_model)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"),
    )
    .managed_access()
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
        version="1.0.0-dev",
        infra_profile=INFRA_PROFILE,
    )
    # REAL MESH WIRING — consume the upstream pharma-sites-demo crosswalk hub DP.
    # This declares the upstream→downstream dependency; the cross-DP join to
    # site_subjects resolves at query time via the live mesh.
    .input(
        "pharma-sites-demo",
        data_product_input()
        .source(
            "https://nxd.nxd.local/data-product/pharma/pharma-sites-demo#/output/port/snowflake"
        )
        .environment("demo"),
    )
    # TRANSFORM: self-seeds the adverse_events base table + the marker row. The
    # auto-generated run_semantic_query compiles SQL against the base table from
    # the kernel-delivered .nxd/semantic/ payloads — no semantic-view DDL needed.
    # .startup_timeout(600) covers cold-boot contention when the mesh launches.
    .transform(
        code(transform)
        .compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute")
        .startup_timeout(600)
    )
    .output(_storage)
    # Auto-wire 4 governed MCP tools (list_models, semantic_model, describe_model,
    # run_semantic_query) reading kernel-delivered payloads.
    .semantic_tools(service="mcp-api-service-k8s")
    # GLOSSARY LINKS — relate this DP to the canonical mesh terms it touches.
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/adverse_event")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/subject")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/site")
)
