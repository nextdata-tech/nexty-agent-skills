"""Models for the pharma-labs (DP_LABS) semantic-layer data product.

The transform seeds this DP's OWN base table (``ASSAYS``) in its own Snowflake
schema (the TRANSFORM-SEED pattern). We promise the REAL ``assays`` model on the
storage port (not a dummy marker), so the discover UI surfaces the actual
attributes, their glossary links, and the cross-DP SEMANTIC RELATIONSHIP. The
``SUBJECT_ID`` attribute ``.referencing(...)``s the subject spine (``subjects``
in pharma-subjects-demo), so the relationship is declared + discoverable across
the mesh. The cross-DP join itself resolves at query time, never in this DP's
single-table view DDL.

__nxd_semantic__ annotations
------------------------------
The kernel reads per-field ``__nxd_semantic__`` JSON blobs from each promised
model's manifest attributes, compiles them into a typed SemanticRegistry, and
delivers the result to the DP pod at boot as
``<root>/.nxd/semantic/<model>.json``. The Python runtime's ``_load_tools()``
merges those files and calls ``build_semantic_tools_from_payload`` to
instantiate the four MCP tools.

NEX-704 MISSING SEAM: ``AttributeSpec`` has no public setter for per-field
metadata. The blobs are injected here by directly writing to the private
``_metadata`` dict on each ``AttributeSpec``. This is a stopgap until NEX-704
lands a public ``AttributeSpec.semantic_annotation(blob)`` API. The injection
is isolated to this module and clearly marked.
"""

import json

from nxd.spec import Predicate, attribute, semantic_model
from nxd.spec._model import AttributeSpec
from nxd.spec.data_types import float64, int64, string


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
# assays — one row per lab assay, grain: ASSAY_ID. MANY assays per subject.
# Confusable metric pair on the TITER column: titer_sum (SUM) vs titer_avg (AVG).
# SUBJECT_ID is the N:1 cross-DP join key into the site_subjects crosswalk hub
# (owned by DP_SITES / pharma-sites-demo). It also `.referencing(...)`s the
# subject spine so the UI SEMANTIC RELATIONSHIP column renders.
# ---------------------------------------------------------------------------

assays_model = (
    semantic_model("assays")
    .description("Lab assays base table (one row per assay).")
    .schema(
        {
            # Grain only — the old registry declared no count metric on ASSAY_ID.
            "ASSAY_ID": _annotate(
                AttributeSpec(name="ASSAY_ID", data_type=int64()),
                {"kind": "grain"},
            ),
            # Cross-DP join key: MANY assays -> one site_subjects crosswalk row
            # (N:1). Only the first hop from this DP's own model is declared here;
            # the crosswalk->spine second hop resolves at the mesh layer.
            "SUBJECT_ID": _annotate(
                attribute(int64(), "SUBJECT_ID").referencing(
                    data_product="pharma-subjects-demo",
                    model="subjects",
                    attribute=["SUBJECT_ID"],
                ),
                {
                    "kind": "join",
                    "to_model": "site_subjects",
                    "to_column": "SUBJECT_ID",
                    "cardinality": "many_to_one",
                },
            ),
            "ASSAY_TYPE": _annotate(
                AttributeSpec(
                    name="ASSAY_TYPE",
                    data_type=string(),
                    _description="Type of lab assay (e.g. ELISA, PCR, titration).",
                ),
                {
                    "kind": "dimension",
                    "name": "assay_type",
                    "description": "Type of lab assay (e.g. ELISA, PCR, titration).",
                    "type": "string",
                },
            ),
            # CONFUSABLE PAIR — same column TITER, two metrics with different aggs.
            "TITER": _annotate(
                AttributeSpec(
                    name="TITER",
                    data_type=float64(),
                    _description="Measured titer across assays.",
                ),
                {
                    "roles": [
                        {
                            "kind": "metric",
                            "name": "titer_sum",
                            "agg": "sum",
                            "description": "Sum of measured titer across assays (total titer).",
                        },
                        {
                            "kind": "metric",
                            "name": "titer_avg",
                            "agg": "avg",
                            "description": "Average measured titer per assay (mean titer level).",
                        },
                    ]
                },
            ),
        }
    )
    # Model-level glossary link + key attribute-level links (render in the UI).
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/assay")
    .link("TITER", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/titer")
    .link("SUBJECT_ID", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/subject")
)

# ---------------------------------------------------------------------------
# Marker model — satisfies the storage port's produce-verification requirement.
# ---------------------------------------------------------------------------

provision_marker = (
    semantic_model("assays_smoke_marker")
    .description("Marker table written by the provisioning transform.")
    .schema(
        {
            "MARKER_ID": int64(),
            "VIEW_NAME": string(),
        }
    )
)
