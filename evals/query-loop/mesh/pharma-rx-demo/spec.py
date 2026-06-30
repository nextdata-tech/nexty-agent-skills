"""spec.py for the pharma-rx-demo (DP_RX) semantic-layer data product.

Four MCP tools (list_models, semantic_model, describe_model, run_semantic_query)
are auto-generated at pod boot via the .semantic_tools() flag (NEX-710 /
PR #6979). The kernel compiles per-field __nxd_semantic__ blobs on each
promised model's manifest attributes into typed SemanticRegistry payloads,
delivers them to ``<root>/.nxd/semantic/<model>.json`` at startup, and the
entrypoints module reads them back to build the four tool closures.

Manifest authoring
------------------
The Python spec author surface for __nxd_semantic__ field annotations
(NEX-704) is not yet merged. The annotations are injected via a private-field
stopgap in models.py:
  AttributeSpec._metadata["__nxd_semantic__"] = json.dumps(role)

Wiring
------
- dispenses + provision_marker promised on the storage port so their annotated
  attributes appear in the kernel's manifest (and thus in .nxd/semantic/*.json
  at pod boot). The dispenses fact carries TWO outbound cross-DP join blobs
  (SUBJECT_ID -> site_subjects, PRODUCT_ID -> products).
- provision_marker is also promised (satisfies produce-verification).
- .semantic_tools() auto-wires 4 RPC tool functions + mcp-api port.
- The transform seeds the base DISPENSES table and writes the marker row.
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
from models import dispenses_model, provision_marker

INFRA_PROFILE = "ecommerce-demo"
SNOWFLAKE_SERVICE = "nxd-snowflake"

# Storage output port named "snowflake" — its name is the transform's parameter
# name, and it supplies the Snowflake connection both the transform (to seed the
# base table + marker) and run_semantic_query (to read it) use. Plain storage(...)
# promising both models so their annotated attributes are included in the
# kernel-generated manifest models section.
_storage = (
    data_product_output()
    # Promise the marker (satisfies produce-verification) and the REAL dispenses
    # model so the discover UI surfaces its attributes + glossary links +
    # cross-DP SEMANTIC RELATIONSHIP. The transform seeds the matching DISPENSES
    # table.
    .promise(provision_marker)
    .promise(dispenses_model)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"),
    )
    .managed_access()
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
        version="1.0.0-dev",
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
    # TRANSFORM: seeds the base DISPENSES table and writes the marker row. No
    # semantic-view DDL needed — the auto-generated run_semantic_query compiles
    # SQL against the base table from the kernel-delivered .nxd/semantic/
    # payloads. .startup_timeout(600) covers cold-boot contention when the mesh
    # launches.
    .transform(
        code(transform).compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute").startup_timeout(600)
    )
    .output(_storage)
    # Auto-wire 4 governed MCP tools (list_models, semantic_model,
    # describe_model, run_semantic_query) reading kernel-delivered payloads.
    .semantic_tools(service="mcp-api-service-k8s")
    # Glossary links — terms this DP relates to (pharma-glossary-demo term ids).
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/dispense")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/subject")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/product")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/prescriber")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/site")
)
