"""Models for the pharma-rx-demo (DP_RX) semantic-layer data product.

The transform seeds the REAL ``DISPENSES`` table; we promise that REAL model on
the storage port (not a dummy marker), so the discover UI surfaces the actual
attributes, their glossary links, and the cross-DP SEMANTIC RELATIONSHIP. As the
MANY-side fact, ``dispenses`` carries outgoing cross-DP references on its foreign
keys: SUBJECT_ID -> pharma-subjects-demo/subjects, PRODUCT_ID ->
pharma-product-demo/products. Model + key attributes link to glossary terms.

This DP owns ONE fact model: ``dispenses`` (grain DISPENSE_ID). MANY dispenses
per subject. Two N:1 joins reach the spine and a far product dimension across DP
boundaries:

    dispenses ─► site_subjects (on subject_id)   [crosswalk hub, DP_SITES]
    dispenses ─► products       (on product_id)  [far dimension, DP_PRODUCT]

Confusable metric pair on this model:
- ``dispense_count``  — COUNT_DISTINCT of DISPENSE_ID (how many dispenses).
- ``units_dispensed`` — SUM of UNITS               (how much was dispensed).

__nxd_semantic__ annotations
------------------------------
The kernel reads per-field ``__nxd_semantic__`` JSON blobs from each promised
model's manifest attributes, compiles them into a typed SemanticRegistry, and
delivers the result to the DP pod at boot as
``<root>/.nxd/semantic/<model>.json``. The Python runtime's ``_load_tools()``
merges those files and calls ``build_semantic_tools_from_payload`` to
instantiate the four MCP tools.

CROSS-DP HANDLING: the foreign target models (``site_subjects``, ``subjects``,
``products``) and their dimensions are NOT declared here — they are published by
the owning DPs (DP_SITES / DP_SUBJECTS / DP_PRODUCT). This DP only annotates the
first-hop join blobs FROM its own ``dispenses`` model: SUBJECT_ID -> site_subjects
and PRODUCT_ID -> products. The site_subjects -> subjects second hop is published
by pharma-sites-demo. Entity/model names are globally unique across the mesh so
bare-name joins resolve against the other DPs' registries at cross-DP plan time.

NEX-704 MISSING SEAM: ``AttributeSpec`` has no public setter for per-field
metadata. The blobs are injected here by directly writing to the private
``_metadata`` dict on each ``AttributeSpec``. This is a stopgap until
NEX-704 lands a public ``AttributeSpec.semantic_annotation(blob)`` API. The
injection is isolated to this module and clearly marked.
"""

import json

from nxd.spec import Predicate, attribute, semantic_model
from nxd.spec._model import AttributeSpec
from nxd.spec.data_types import int64, string


# ---------------------------------------------------------------------------
# Internal helper: inject a __nxd_semantic__ blob into an AttributeSpec.
# Replace with AttributeSpec.semantic_annotation() once NEX-704 ships.
# ---------------------------------------------------------------------------
_SEMANTIC_KEY = "__nxd_semantic__"


def _annotate(attr: AttributeSpec, role: dict) -> AttributeSpec:
    """Inject a single-role ``__nxd_semantic__`` blob into *attr*._metadata.

    Uses the bare single-role shorthand accepted by ``FieldAnnotation.from_value``
    (``{"kind": ...}`` without a ``roles`` wrapper). Mutates *attr* in-place and
    returns it for chaining.

    This is the NEX-704 stopgap. Remove once ``AttributeSpec.semantic_annotation``
    is public.
    """
    attr._metadata[_SEMANTIC_KEY] = json.dumps(role, separators=(",", ":"))
    return attr


# ---------------------------------------------------------------------------
# dispenses — one row per medication dispense, grain: DISPENSE_ID
# MANY dispenses per subject. N:1 joins to site_subjects (on SUBJECT_ID) and
# products (on PRODUCT_ID), both reaching across DP boundaries.
# ---------------------------------------------------------------------------

dispenses_model = (
    semantic_model("dispenses")
    .description("One row per medication dispense. MANY dispenses per subject.")
    .schema(
        {
            "DISPENSE_ID": _annotate(
                AttributeSpec(
                    name="DISPENSE_ID",
                    data_type=int64(),
                    _description="Unique dispense identifier (grain).",
                ),
                {"kind": "grain"},
            ),
            # Cross-DP FK -> subject spine owned by pharma-subjects-demo, joined
            # via the site_subjects crosswalk hub (N:1). Keep the existing
            # .referencing(...) and wrap it with the first-hop join blob.
            "SUBJECT_ID": _annotate(
                attribute(int64(), "SUBJECT_ID", "Subject the product was dispensed to.")
                .referencing(
                    data_product="pharma-subjects-demo",
                    model="subjects",
                    attribute=["SUBJECT_ID"],
                ),
                {
                    "kind": "join",
                    "to_model": "site_subjects",
                    "to_column": "SUBJECT_ID",
                    "cardinality": "many_to_one",
                    # CROSS-DP edge: site_subjects owned by pharma-sites-demo, not
                    # declared here — owner label carries the join through compile.
                    "to_data_product": "pharma-sites-demo",
                },
            ),
            # Cross-DP FK -> product dimension owned by pharma-product-demo (N:1).
            "PRODUCT_ID": _annotate(
                attribute(int64(), "PRODUCT_ID", "Product that was dispensed.")
                .referencing(
                    data_product="pharma-product-demo",
                    model="products",
                    attribute=["PRODUCT_ID"],
                ),
                {
                    "kind": "join",
                    "to_model": "products",
                    "to_column": "PRODUCT_ID",
                    "cardinality": "many_to_one",
                    # CROSS-DP edge: products owned by pharma-product-demo, not
                    # declared here — owner label carries the join through compile.
                    "to_data_product": "pharma-product-demo",
                },
            ),
            "UNITS": _annotate(
                AttributeSpec(
                    name="UNITS",
                    data_type=int64(),
                    _description="Units dispensed in this event.",
                ),
                {
                    "kind": "metric",
                    "name": "units_dispensed",
                    "agg": "sum",
                    "description": "Total units dispensed (how much medication was dispensed).",
                },
            ),
            "DISPENSE_CHANNEL": _annotate(
                AttributeSpec(
                    name="DISPENSE_CHANNEL",
                    data_type=string(),
                    _description="Channel the dispense was fulfilled through (retail, mail-order, specialty).",
                ),
                {
                    "kind": "dimension",
                    "name": "dispense_channel",
                    "description": "Channel the dispense was fulfilled through (e.g. retail, mail-order).",
                    "type": "string",
                },
            ),
            # PII: National Provider Identifier of the prescribing clinician.
            "PRESCRIBER_NPI": _annotate(
                AttributeSpec(
                    name="PRESCRIBER_NPI",
                    data_type=string(),
                    _description="National Provider Identifier of the prescribing clinician.",
                ),
                {
                    "kind": "dimension",
                    "name": "prescriber_npi",
                    "description": "National Provider Identifier of the prescribing clinician.",
                    "type": "string",
                    "pii": True,
                },
            ),
        }
    )
    # Glossary links at the model + attribute level (render in the UI).
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/dispense")
    .link("PRESCRIBER_NPI", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/prescriber")
    .link("PRODUCT_ID", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/product")
    .link("SUBJECT_ID", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/subject")
)

# ---------------------------------------------------------------------------
# CONFUSABLE-metric pair on the grain column.
# DISPENSE_ID carries BOTH a grain role and a count_distinct metric role
# (dispense_count). The schema dict above annotated it with a bare
# {"kind": "grain"} blob; we patch a full roles list in post-hoc because the
# NEX-704 stopgap (`_annotate` writing AttributeSpec._metadata directly) has no
# shorthand for declaring multiple roles on one column inline. The roles list
# REPLACES the bare-grain blob.
# ---------------------------------------------------------------------------
_annotate(
    dispenses_model._attributes["DISPENSE_ID"],
    {
        "roles": [
            {"kind": "grain"},
            {
                "kind": "metric",
                "name": "dispense_count",
                "agg": "count_distinct",
                "description": "Number of distinct dispenses (how many dispenses occurred).",
            },
        ]
    },
)

# ---------------------------------------------------------------------------
# Marker model — satisfies the storage port's produce-verification requirement.
# The kernel checks at least one model is produced; this tiny table confirms
# the transform ran without promising the self-seeded query tables.
# ---------------------------------------------------------------------------

provision_marker = (
    semantic_model("dispenses_smoke_marker")
    .description("Marker table written by the provisioning transform.")
    .schema(
        {
            "MARKER_ID": int64(),
            "VIEW_NAME": string(),
        }
    )
)
