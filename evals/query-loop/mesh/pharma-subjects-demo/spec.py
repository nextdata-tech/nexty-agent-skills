"""spec.py for pharma-subjects-demo — the SUBJECT SPINE of the fresh pharma mesh.

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
- subjects (the real spine model) is promised on the storage port so its
  annotated attributes appear in the kernel's manifest (and thus in
  .nxd/semantic/*.json at pod boot).
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
from models import subjects_model, provision_marker

INFRA_PROFILE = "ecommerce-demo"
SNOWFLAKE_SERVICE = "nxd-snowflake"

# Storage output port named "snowflake" — promises the marker (produce-
# verification target) and the REAL subjects model so its annotated attributes
# and glossary links are included in the kernel-generated manifest. The kernel
# compiles __nxd_semantic__ blobs from those attributes and delivers a
# .nxd/semantic/<model>.json payload per annotated model at boot.
_storage = (
    data_product_output()
    .promise(provision_marker)
    .promise(subjects_model)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"),
    )
    .managed_access()
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
        version="1.0.0-dev",
        infra_profile=INFRA_PROFILE,
    )
    # Transform seeds the subjects base table and writes the subjects_smoke_marker
    # row. No semantic-view DDL needed — the auto-generated run_semantic_query
    # compiles SQL against the base table from the kernel-delivered
    # .nxd/semantic/ payloads. .startup_timeout(600) covers cold-boot contention
    # when the mesh launches.
    .transform(
        code(transform)
        .compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute")
        .startup_timeout(600)
    )
    .output(_storage)
    # Deploy on the `demo` env so downstream DPs whose
    # `.input(...).environment("demo")` reference this spine resolve it at
    # `pharma-subjects-demo-demo` (the crosswalk hub's upstream-loader 404s
    # otherwise — the upstream must live where the input says it does).
    .environment("demo")
    # Auto-wire 4 governed MCP tools (list_models, semantic_model, describe_model,
    # run_semantic_query) reading kernel-delivered payloads.
    .semantic_tools(service="mcp-api-service-k8s")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/subject")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/subject_country")
)
