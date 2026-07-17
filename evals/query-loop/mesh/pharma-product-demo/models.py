"""Models for pharma-product-demo — the PRODUCT far dimension of the mesh.

The transform seeds the real ``PRODUCTS`` table; we promise that REAL model on the
storage port (not a dummy marker), so the discover UI surfaces the actual
attributes and their glossary links. ``products`` is a FAR dimension / ONE-side
target, so it has no outgoing cross-DP reference; its attributes link to glossary
terms.

__nxd_semantic__ annotations
------------------------------
The kernel reads per-field ``__nxd_semantic__`` JSON blobs from each promised
model's manifest attributes, compiles them into a typed SemanticRegistry, and
delivers the result to the DP pod at boot as
``<root>/.nxd/semantic/<model>.json``. The Python runtime's ``_load_tools()``
merges those files and calls ``build_semantic_tools_from_payload`` to instantiate
the four MCP tools.

NEX-704 MISSING SEAM: ``AttributeSpec`` has no public setter for per-field
metadata. The blobs are injected here by directly writing to the private
``_metadata`` dict on each ``AttributeSpec``. This is a stopgap until NEX-704
lands a public ``AttributeSpec.semantic_annotation(blob)`` API. The injection is
isolated to this module and clearly marked.
"""

import json

from nxd.spec import Predicate, semantic_model
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
# products — one row per product (drug / therapeutic agent), grain: PRODUCT_ID
# `products` is a FAR dimension / ONE-side target — no outgoing joins.
# ---------------------------------------------------------------------------

products_model = (
    semantic_model("products")
    .description("Product dimension — one row per product (drug / therapeutic agent).")
    .schema(
        {
            "PRODUCT_ID": _annotate(
                AttributeSpec(name="PRODUCT_ID", data_type=int64()),
                {"kind": "grain"},
            ),
            "PRODUCT_NAME": _annotate(
                AttributeSpec(
                    name="PRODUCT_NAME",
                    data_type=string(),
                    _description="Human-readable product name.",
                ),
                {
                    "kind": "dimension",
                    "name": "product_name",
                    "description": "Human-readable product name.",
                    "type": "string",
                },
            ),
            "MODALITY": _annotate(
                AttributeSpec(
                    name="MODALITY",
                    data_type=string(),
                    _description="Therapeutic modality (e.g. antibody, small_molecule, vaccine).",
                ),
                {
                    "kind": "dimension",
                    "name": "modality",
                    "description": "Therapeutic modality (e.g. antibody, small_molecule, vaccine).",
                    "type": "string",
                },
            ),
        }
    )
    # Glossary links at the model + attribute level (render in the UI).
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/product")
    .link("PRODUCT_NAME", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/product")
)

# ---------------------------------------------------------------------------
# product_count metric anchored on the grain column (COUNT_DISTINCT(PRODUCT_ID)).
# PRODUCT_ID carries BOTH a grain role and a metric role. The schema dict above
# annotated it with a bare {"kind": "grain"} blob; we patch a full roles list in
# post-hoc because the NEX-704 spec stopgap (`_annotate` writing
# AttributeSpec._metadata directly) has no shorthand for declaring multiple roles
# on one column inline. The roles list REPLACES the bare-grain blob.
# ---------------------------------------------------------------------------
_annotate(
    products_model._attributes["PRODUCT_ID"],
    {
        "roles": [
            {"kind": "grain"},
            {
                "kind": "metric",
                "name": "product_count",
                "agg": "count_distinct",
                "description": "Distinct number of products.",
            },
        ]
    },
)

# ---------------------------------------------------------------------------
# Marker model — satisfies the storage port's produce-verification requirement.
# The kernel checks at least one model is produced; this tiny table confirms the
# transform ran without promising the self-seeded query tables.
# ---------------------------------------------------------------------------

provision_marker = (
    semantic_model("products_smoke_marker")
    .description("Marker table written by the provisioning transform.")
    .schema(
        {
            "MARKER_ID": int64(),
            "VIEW_NAME": string(),
        }
    )
)
