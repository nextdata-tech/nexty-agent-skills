"""spec.py for DP_SITES (pharma-sites-demo) — the MANY_TO_MANY crosswalk hub.

Four MCP tools (list_models, semantic_model, describe_model, run_semantic_query)
are auto-generated at pod boot via the ``.semantic_tools()`` flag (NEX-710 /
PR #6979). The kernel compiles per-field ``__nxd_semantic__`` blobs on each
promised model's manifest attributes into typed SemanticRegistry payloads,
delivers them to ``<root>/.nxd/semantic/<model>.json`` at startup, and the
entrypoints module reads them back to build the four tool closures.

Cross-DP wiring
---------------
This DP is the crosswalk hub. The cross-DP edge to the subject spine
(pharma-subjects-demo/subjects) is published by the ``join`` blob on
``site_subjects.SUBJECT_ID`` (in models.py) — NOT by redeclaring the foreign
model here. The mesh resolves the foreign dimensions at query time.

Wiring
------
- sites + site_subjects promised on the storage port so their annotated
  attributes appear in the kernel's manifest (and thus in .nxd/semantic/*.json
  at pod boot). EVERY annotated model is promised so its payload is delivered.
- provision_marker is also promised (satisfies produce-verification).
- .semantic_tools() auto-wires 4 RPC tool functions + mcp-api port.
- The transform self-seeds the base tables and writes the marker row. No
  semantic-view DDL / registry.py / tools.py / provision.py needed.
"""

from nxd.spec import (
    code,
    data_product,
    data_product_input,
    data_product_output,
    storage,
    Predicate,
)
from transform import transform
from models import sites_model, site_subjects_model, provision_marker

INFRA_PROFILE = "ecommerce-demo"
SNOWFLAKE_SERVICE = "nxd-snowflake"

# Storage output port named "snowflake" — its name is the transform's parameter
# name, and it supplies the Snowflake connection the transform uses to seed the
# base tables. PLAIN storage(...) — NO as_view (self-seed pattern).
#
# Promise EVERY annotated model so its __nxd_semantic__ payload reaches the
# manifest (and thus .nxd/semantic/<model>.json at boot): the marker (produce-
# verification), the crosswalk hub (cross-DP join blobs + grain), AND the sites
# dimension (site_region dim + site_count metric).
_storage = (
    data_product_output()
    .promise(provision_marker)
    .promise(site_subjects_model)
    .promise(sites_model)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"),
    )
    .managed_access()
)

spec = (
    data_product(
        name="pharma-sites-demo",
        domain="pharma",
        description=(
            "DP_SITES — the MANY_TO_MANY crosswalk hub of the pharma mesh. "
            "Models the site_subjects crosswalk (grain site_id, subject_id) "
            "joining the subject spine to the sites dimension, plus the sites "
            "dimension itself. Exposes governed metrics and dimensions via MCP "
            "so agents can answer natural-language questions without raw SQL."
        ),
        version="1.0.0-dev",
        infra_profile=INFRA_PROFILE,
    )
    # REAL MESH WIRING — this crosswalk hub consumes the subject spine upstream.
    # The .input(...) declares the real upstream->downstream dependency on the
    # subject-spine DP's snowflake output port (placed BEFORE .transform()).
    .input(
        "pharma-subjects-demo",
        data_product_input()
        .source(
            "https://nxd.nxd.local/data-product/pharma/pharma-subjects-demo#/output/port/snowflake"
        )
        .environment("demo"),
    )
    # TRANSFORM: self-seeds the SITES + SITE_SUBJECTS base tables and writes the
    # sites_smoke_marker row. The auto-generated run_semantic_query compiles SQL
    # against the base tables from the kernel-delivered .nxd/semantic/ payloads —
    # no semantic-view DDL needed. .startup_timeout(600) covers cold-boot
    # contention when the mesh launches.
    .transform(
        code(transform).compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute").startup_timeout(600)
    )
    .output(_storage)
    # Glossary links — tie this DP to the governed pharma glossary terms it
    # surfaces (the `site` dimension it owns + the `subject` spine it crosswalks).
    .link(
        Predicate.GlossaryTerm,
        "/data-product/demo/pharma-glossary-demo#/terms/site",
    )
    .link(
        Predicate.GlossaryTerm,
        "/data-product/demo/pharma-glossary-demo#/terms/subject",
    )
    # Auto-wire 4 governed MCP tools (list_models, semantic_model, describe_model,
    # run_semantic_query) reading kernel-delivered payloads.
    .semantic_tools(service="mcp-api-service-k8s")
)
