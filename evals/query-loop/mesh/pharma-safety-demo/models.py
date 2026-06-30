"""Models for pharma-safety-demo — the FAR ADVERSE-EVENTS FACT of the mesh.

NEW `.semantic_tools()` pattern (NEX-710). This DP owns ONE fact model:
``adverse_events`` (grain AE_ID, one row per adverse event, MANY adverse events
per subject). Its per-field semantics are declared via ``__nxd_semantic__`` JSON
blobs injected onto each ``AttributeSpec`` (the NEX-704 stopgap below). The kernel
compiles those blobs into a typed SemanticRegistry, delivers it to the DP pod at
boot as ``<root>/.nxd/semantic/<model>.json``, and ``.semantic_tools()`` wires up
the four MCP tools from that payload — no hand-authored registry.py / tools.py.

Confusable metric pair (intent-gate stressor): ``ae_count`` is a plain
COUNT_DISTINCT of AE_ID (so AE_ID carries BOTH grain and metric roles);
``serious_ae_count`` is a CASE-SUM over the IS_SERIOUS boolean flag
(``boolean: true`` — NOT a numeric SUM of a numeric column). A loosely-worded
"adverse events" must pick ae_count; "serious adverse events" must pick
serious_ae_count.

CROSS-DP: ``adverse_events`` joins MANY_TO_ONE to ``site_subjects`` (owned by the
sibling pharma-sites-demo DP) on SUBJECT_ID. The foreign model + its dimensions
are NOT declared here — only the join annotation on the FK column, which resolves
at the mesh layer (entity names are globally unique across the mesh).

__nxd_semantic__ annotations
------------------------------
NEX-704 MISSING SEAM: ``AttributeSpec`` has no public setter for per-field
metadata. The blobs are injected here by directly writing to the private
``_metadata`` dict on each ``AttributeSpec``. This is a stopgap until NEX-704
lands a public ``AttributeSpec.semantic_annotation(blob)`` API. The injection is
isolated to this module and clearly marked.
"""

import json

from nxd.spec import Predicate, attribute, semantic_model
from nxd.spec._model import AttributeSpec
from nxd.spec.data_types import boolean, int64, string


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
# adverse_events — one row per adverse event, grain: AE_ID.
# MANY adverse events per subject; N:1 cross-DP join to site_subjects.
# ---------------------------------------------------------------------------

adverse_events_model = (
    semantic_model("adverse_events")
    .description("Adverse-events fact — one row per adverse event (grain AE_ID).")
    .schema(
        {
            # AE_ID: grain + the ae_count count-distinct metric (multi-role).
            "AE_ID": _annotate(
                AttributeSpec(name="AE_ID", data_type=int64()),
                {
                    "roles": [
                        {"kind": "grain"},
                        {
                            "kind": "metric",
                            "name": "ae_count",
                            "agg": "count_distinct",
                            "description": "Number of distinct adverse events (all severities).",
                        },
                    ]
                },
            ),
            # SUBJECT_ID: cross-DP FK to the subject spine (fills the UI SEMANTIC
            # RELATIONSHIP column) AND the N:1 join key to the site_subjects
            # crosswalk hub (owned by pharma-sites-demo). The foreign model is NOT
            # declared here; the join resolves at the mesh layer.
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
            "AE_TERM": _annotate(
                AttributeSpec(
                    name="AE_TERM",
                    data_type=string(),
                    _description="MedDRA-style adverse-event term (e.g. headache, nausea).",
                ),
                {
                    "kind": "dimension",
                    "name": "ae_term",
                    "description": "MedDRA-style adverse-event term (e.g. headache, nausea).",
                    "type": "string",
                },
            ),
            # IS_SERIOUS: boolean flag the serious_ae_count metric CASE-sums over.
            # boolean=True is REQUIRED — this is a CASE-sum over the boolean flag
            # (counts rows where IS_SERIOUS is true), NOT a numeric SUM.
            "IS_SERIOUS": _annotate(
                AttributeSpec(name="IS_SERIOUS", data_type=boolean()),
                {
                    "kind": "metric",
                    "name": "serious_ae_count",
                    "agg": "sum",
                    "boolean": True,
                    "description": (
                        "Number of SERIOUS adverse events — a CASE-sum over the IS_SERIOUS "
                        "boolean flag (counts rows where IS_SERIOUS is true), NOT a numeric "
                        "SUM. Use only when the question asks specifically for SERIOUS events."
                    ),
                },
            ),
        }
    )
    # Model-level glossary link to the canonical `adverse_event` term.
    .link(Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/adverse_event")
    # Attribute-level glossary links (field-name overload).
    .link("SUBJECT_ID", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/subject")
    .link("AE_TERM", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/adverse_event")
    .link("IS_SERIOUS", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/serious_ae")
)

# ---------------------------------------------------------------------------
# Marker model — satisfies the storage port's produce-verification requirement.
# The kernel checks at least one model is produced; this tiny table confirms the
# transform ran without promising the self-seeded query table's full shape.
# ---------------------------------------------------------------------------

provision_marker = (
    semantic_model("adverse_events_smoke_marker")
    .description("Marker table written by the provisioning transform.")
    .schema(
        {
            "MARKER_ID": int64(),
            "VIEW_NAME": string(),
        }
    )
)
