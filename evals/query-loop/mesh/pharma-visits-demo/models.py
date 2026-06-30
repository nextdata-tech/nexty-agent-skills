"""Models for the pharma-visits (DP_VISITS) semantic-layer data product.

This DP owns ONE fact model: ``visits`` (grain VISIT_ID). MANY visits per
subject. The transform seeds the real ``VISITS`` fact table; we promise that
REAL model on the storage port (not a dummy marker), so the discover UI surfaces
the actual attributes, their glossary links, and the cross-DP SEMANTIC
RELATIONSHIP. The ``visits`` fact carries an outgoing cross-DP reference on
SUBJECT_ID into the crosswalk hub ``site_subjects`` (owned by pharma-sites-demo);
its attributes link to glossary terms.

__nxd_semantic__ annotations
------------------------------
The kernel reads per-field ``__nxd_semantic__`` JSON blobs from each promised
model's manifest attributes, compiles them into a typed SemanticRegistry, and
delivers the result to the DP pod at boot as
``<root>/.nxd/semantic/<model>.json``. The Python runtime's ``_load_tools()``
merges those files and calls ``build_semantic_tools_from_payload`` to instantiate
the four MCP tools.

CROSS-DP HANDLING: this DP declares ONLY the join FROM its own ``visits`` fact —
the first hop to the crosswalk ``site_subjects`` on SUBJECT_ID (MANY_TO_ONE).
The further hop (site_subjects → subjects) and the foreign spine dimensions
(subject_country, subject_mrn) are NOT redeclared here — that edge is published
by pharma-sites-demo and the mesh resolves it at query time.

CONFUSABLE PAIR (cross-grain): visit_count (how many visits, this model) vs
subject_count (how many subjects, owned by pharma-subjects-demo's ``subjects``
model). "how many visits" must resolve to visit_count here, NOT subject_count.

NEX-704 MISSING SEAM: ``AttributeSpec`` has no public setter for per-field
metadata. The blobs are injected here by directly writing to the private
``_metadata`` dict on each ``AttributeSpec``. This is a stopgap until NEX-704
lands a public ``AttributeSpec.semantic_annotation(blob)`` API. The injection is
isolated to this module and clearly marked.
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
# visits — one row per clinical visit, grain: VISIT_ID. MANY visits per subject.
# N:1 join to the crosswalk hub site_subjects on SUBJECT_ID (cross-DP first hop).
# ---------------------------------------------------------------------------

visits_model = (
    semantic_model("visits")
    .description("One row per clinical visit. MANY visits per subject.")
    .schema(
        {
            "VISIT_ID": _annotate(
                AttributeSpec(name="VISIT_ID", data_type=int64()),
                {"kind": "grain"},
            ),
            # Cross-DP FK into the subject spine (owned by pharma-subjects-demo).
            # The join blob declares only this DP's OWN first hop: many visits ->
            # one site_subjects crosswalk row (N:1). The further hop + foreign
            # spine dimensions are published by pharma-sites-demo / resolved at
            # the mesh layer.
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
            "VISIT_TYPE": _annotate(
                AttributeSpec(
                    name="VISIT_TYPE",
                    data_type=string(),
                    _description="Type of clinical visit (e.g. screening, baseline, follow-up).",
                ),
                {
                    "kind": "dimension",
                    "name": "visit_type",
                    "description": "Type of clinical visit (e.g. screening, baseline, follow-up).",
                    "type": "string",
                },
            ),
            "DURATION_MIN": _annotate(
                AttributeSpec(
                    name="DURATION_MIN",
                    data_type=float64(),
                    _description="Clinical-visit duration in minutes.",
                ),
                {
                    "kind": "metric",
                    "name": "visit_duration_min",
                    "agg": "sum",
                    "description": "Total clinical-visit duration in minutes (sum of visit durations).",
                },
            ),
        }
    )
    # Glossary links at the model + attribute level (render in the UI).
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/visit")
    .link("VISIT_TYPE", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/visit")
    .link("SUBJECT_ID", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/subject")
)

# ---------------------------------------------------------------------------
# visit_count metric — count_distinct on VISIT_ID. VISIT_ID carries BOTH a grain
# role and a metric role. The schema dict above annotated it with a bare
# {"kind": "grain"} blob; we patch a full roles list in post-hoc because the
# NEX-704 stopgap (_annotate writing AttributeSpec._metadata directly) has no
# shorthand for declaring multiple roles on one column inline. The roles list
# REPLACES the bare-grain blob.
# ---------------------------------------------------------------------------
_annotate(
    visits_model._attributes["VISIT_ID"],
    {
        "roles": [
            {"kind": "grain"},
            {
                "kind": "metric",
                "name": "visit_count",
                "agg": "count_distinct",
                "description": "Number of distinct clinical visits (how many visits).",
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
    semantic_model("visits_smoke_marker")
    .description("Marker table written by the provisioning transform.")
    .schema(
        {
            "MARKER_ID": int64(),
            "VIEW_NAME": string(),
        }
    )
)
