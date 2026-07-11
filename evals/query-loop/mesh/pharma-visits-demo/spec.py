"""spec.py for the pharma-visits (DP_VISITS) semantic-layer data product.

Four MCP tools (list_models, semantic_model, describe_model, run_semantic_query)
are auto-generated at pod boot via the .semantic_tools() flag (NEX-710 /
PR #6979). The kernel compiles per-field __nxd_semantic__ blobs on each promised
model's manifest attributes into typed SemanticRegistry payloads, delivers them
to ``<root>/.nxd/semantic/<model>.json`` at startup, and the entrypoints module
reads them back to build the four tool closures.

Manifest authoring
------------------
The Python spec author surface for __nxd_semantic__ field annotations (NEX-704)
is not yet merged. The annotations are injected in models.py via a private-field
stopgap:
  AttributeSpec._metadata["__nxd_semantic__"] = json.dumps(role)

Wiring
------
- visits is promised on the storage port so its annotated attributes appear in
  the kernel's manifest (and thus in .nxd/semantic/*.json at pod boot).
- provision_marker is also promised (satisfies produce-verification).
- .semantic_tools() auto-wires 4 RPC tool functions + mcp-api port.
- The transform seeds the visits base table and writes the marker row.

CROSS-DP MESH WIRING: this DP consumes the upstream pharma-sites-demo output
port (.input below) and declares only its OWN first join hop (visits ->
site_subjects on SUBJECT_ID) in models.py; the further hop into the subject
spine + the foreign dimensions are resolved at the mesh layer.
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
from models import visits_model, provision_marker

INFRA_PROFILE = "ecommerce-demo"
SNOWFLAKE_SERVICE = "nxd-snowflake"

# Storage output port named "snowflake" — its name is the transform's parameter
# name, and it supplies the Snowflake connection the transform uses to seed the
# table + write the marker, and run_semantic_query uses to read it. Promises both
# models so their annotated attributes are included in the kernel-generated
# manifest models section. Plain storage(...) — NO as_view (self-seed pattern).
_storage = (
    data_product_output()
    .promise(provision_marker)
    .promise(visits_model)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"),
    )
    .managed_access()
)

spec = (
    data_product(
        name="pharma-visits-demo",
        domain="pharma",
        description=(
            "Semantic-layer data product over clinical visits (one row per "
            "visit, MANY visits per subject). Exposes governed metrics "
            "(visit_count, visit_duration_min) and the visit_type dimension via "
            "MCP, joined MANY_TO_ONE through site_subjects into the subject "
            "spine, so agents answer natural-language questions without raw SQL."
        ),
        version="1.0.0-dev",
        infra_profile=INFRA_PROFILE,
    )
    # REAL MESH WIRING — consume the upstream pharma-sites-demo output port. This
    # declares the real upstream→downstream dependency in the mesh.
    .input(
        "pharma-sites-demo",
        data_product_input()
        .source(
            "https://nxd.nxd.local/data-product/pharma/pharma-sites-demo#/output/port/snowflake"
        )
        .environment("demo"),
    )
    # TRANSFORM: seeds the visits base table and writes the visits_smoke_marker
    # row. No semantic-view DDL needed — the auto-generated run_semantic_query
    # compiles SQL against the base table from the kernel-delivered
    # .nxd/semantic/ payloads. .startup_timeout(600) covers cold-boot contention.
    .transform(
        code(transform)
        .compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute")
        .startup_timeout(600)
    )
    .output(_storage)
    # Deploy on the `demo` env so this fact's `.input(...).environment("demo")`
    # edges resolve against the demo-env upstreams. Whole mesh on one env.
    .environment("demo")
    # Auto-wire 4 governed MCP tools (list_models, semantic_model,
    # describe_model, run_semantic_query) reading kernel-delivered payloads.
    .semantic_tools(service="mcp-api-service-k8s")
    # ── Glossary links — terms this DP relates to (owned in pharma-glossary-demo) ──
    .link(
        Predicate.GlossaryTerm,
        "/data-product/demo/pharma-glossary-demo#/terms/visit",
    )
    .link(
        Predicate.GlossaryTerm,
        "/data-product/demo/pharma-glossary-demo#/terms/subject",
    )
    .link(
        Predicate.GlossaryTerm,
        "/data-product/demo/pharma-glossary-demo#/terms/site",
    )
)
