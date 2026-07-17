"""Models for pharma-subjects-demo — the SUBJECT SPINE of the mesh.

The transform seeds the real ``SUBJECTS`` table; we promise that REAL model on the
storage port (not a dummy marker), so the discover UI surfaces the actual
attributes, their glossary links, and (on downstream facts) the cross-DP
SEMANTIC RELATIONSHIP. ``subjects`` is the spine, so it has no outgoing cross-DP
reference; its attributes link to glossary terms.

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
# subjects — the SUBJECT SPINE. One row per enrolled clinical-trial subject.
# grain: SUBJECT_ID. No joins (this DP IS the spine).
# ---------------------------------------------------------------------------

subjects_model = (
    semantic_model("subjects")
    .description("Subject spine — one row per enrolled clinical-trial subject.")
    .schema(
        {
            "SUBJECT_ID": _annotate(
                AttributeSpec(name="SUBJECT_ID", data_type=int64()),
                {"kind": "grain"},
            ),
            "SUBJECT_COUNTRY": _annotate(
                AttributeSpec(
                    name="SUBJECT_COUNTRY",
                    data_type=string(),
                    _description="Subject's country of enrollment.",
                ),
                {
                    "kind": "dimension",
                    "name": "subject_country",
                    "description": "Subject's country of enrollment.",
                    "type": "string",
                },
            ),
            "SUBJECT_MRN": _annotate(
                AttributeSpec(
                    name="SUBJECT_MRN",
                    data_type=string(),
                    _description="Subject medical record number (PII).",
                ),
                {
                    "kind": "dimension",
                    "name": "subject_mrn",
                    "description": "Subject medical record number (PII).",
                    "type": "string",
                    "pii": True,
                },
            ),
        }
    )
    # Glossary links at the model + attribute level (render in the UI).
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/subject")
    .link("SUBJECT_COUNTRY", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/subject_country")
)

# ---------------------------------------------------------------------------
# subject_count metric on the grain column: COUNT_DISTINCT(SUBJECT_ID).
# SUBJECT_ID carries BOTH a grain role and a count_distinct metric role. The
# schema dict above annotated it with a bare {"kind": "grain"} blob; we patch a
# full roles list in post-hoc because the NEX-704 spec stopgap (`_annotate`
# writing AttributeSpec._metadata directly) has no shorthand for declaring
# multiple roles on one column inline. The roles list REPLACES the bare-grain blob.
# ---------------------------------------------------------------------------
_annotate(
    subjects_model._attributes["SUBJECT_ID"],
    {
        "roles": [
            {"kind": "grain"},
            {
                "kind": "metric",
                "name": "subject_count",
                "agg": "count_distinct",
                "description": "Distinct number of subjects.",
            },
        ]
    },
)

# ---------------------------------------------------------------------------
# Marker model — satisfies the storage port's produce-verification requirement.
# The kernel checks at least one model is produced; this tiny table confirms
# the transform ran.
# ---------------------------------------------------------------------------

provision_marker = (
    semantic_model("subjects_smoke_marker")
    .description("Marker table written by the provisioning transform.")
    .schema(
        {
            "MARKER_ID": int64(),
            "VIEW_NAME": string(),
        }
    )
)
