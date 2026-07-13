"""Models for DP_SITES (pharma-sites-demo) — the MANY_TO_MANY crosswalk HUB.

This DP owns TWO real models, both seeded by the transform and promised on the
storage port so their per-field ``__nxd_semantic__`` annotations reach the
kernel-generated manifest:

  - ``sites`` (grain SITE_ID) — the site dimension. Carries the
    ``site_region`` dimension and the ``site_count`` count-distinct metric.
  - ``site_subjects`` (grain "SITE_ID, SUBJECT_ID") — the fan-out crosswalk hub.
    SITE_ID joins MANY_TO_ONE to this DP's own ``sites``; SUBJECT_ID joins
    MANY_TO_ONE to the subject spine (pharma-subjects-demo/subjects).

CROSS-DP HANDLING (NEW pattern)
-------------------------------
The OLD registry.py declared FOREIGN stub models (``subjects`` with
``data_product="pharma-subjects-demo"``) plus their dimensions
(subject_country, subject_mrn) and explicit joins. In the NEW ``__nxd_semantic__``
pattern we do NOT redeclare foreign models or their dimensions — those live on
the owning DP. Instead the crosswalk's OWN join-key columns carry a ``join`` blob
(``to_model``/``to_column``/``cardinality``) that publishes the cross-DP edge;
the mesh resolves the foreign dimensions at query time. SUBJECT_ID's join blob
points at the foreign ``subjects`` model; SITE_ID's points at this DP's ``sites``.

__nxd_semantic__ annotations
----------------------------
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
    """Inject a ``__nxd_semantic__`` blob into *attr*._metadata.

    Accepts either the bare single-role shorthand (``{"kind": ...}``) or the
    multi-role form (``{"roles": [...]}``) understood by
    ``FieldAnnotation.from_value``. Mutates *attr* in-place and returns it for
    chaining.

    This is the NEX-704 stopgap. Remove once ``AttributeSpec.semantic_annotation``
    is public.
    """
    attr._metadata[_SEMANTIC_KEY] = json.dumps(role, separators=(",", ":"))
    return attr


# ---------------------------------------------------------------------------
# sites — one row per clinical trial site, grain: SITE_ID
# SITE_ID carries grain + the site_count count-distinct metric.
# SITE_REGION is the site_region dimension.
# ---------------------------------------------------------------------------

sites_model = (
    semantic_model("sites")
    .description("One row per clinical trial site.")
    .schema(
        {
            # SITE_ID: grain + site_count (COUNT_DISTINCT(SITE_ID)) metric.
            "SITE_ID": _annotate(
                AttributeSpec(name="SITE_ID", data_type=int64()),
                {
                    "roles": [
                        {"kind": "grain"},
                        {
                            "kind": "metric",
                            "name": "site_count",
                            "agg": "count_distinct",
                            "description": "Distinct number of clinical trial sites.",
                        },
                    ]
                },
            ),
            "SITE_REGION": _annotate(
                AttributeSpec(
                    name="SITE_REGION",
                    data_type=string(),
                    _description="Geographic region the site belongs to.",
                ),
                {
                    "kind": "dimension",
                    "name": "site_region",
                    "description": "Geographic region the site belongs to.",
                    "type": "string",
                },
            ),
        }
    )
    # Glossary link — the `site` term this dimension owns.
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/site")
)

# ---------------------------------------------------------------------------
# site_subjects — the MANY_TO_MANY crosswalk HUB, grain: "SITE_ID, SUBJECT_ID"
#
# Both grain columns ALSO carry a cross-DP FK lineage edge (.referencing) AND a
# semantic join role. Each is wrapped with _annotate(attribute(...).referencing(...))
# so the column carries BOTH the lineage edge and the multi-role grain+join blob:
#   - SITE_ID    → this DP's own sites (FK + MANY_TO_ONE join to sites)
#   - SUBJECT_ID → pharma-subjects-demo/subjects (FK + MANY_TO_ONE join to subjects)
# ---------------------------------------------------------------------------

site_subjects_model = (
    semantic_model("site_subjects")
    .description(
        "Crosswalk hub — one row per (site, subject) enrollment, "
        "MANY_TO_MANY fan-out linking the subject spine to the site dimension."
    )
    .schema(
        {
            # SITE_ID → this DP's own sites dimension.
            # grain + MANY_TO_ONE join to sites; FK lineage edge preserved.
            "SITE_ID": _annotate(
                attribute(int64(), "SITE_ID").referencing(
                    data_product="pharma-sites-demo",
                    model="sites",
                    attribute=["SITE_ID"],
                ),
                {
                    "roles": [
                        {"kind": "grain"},
                        {
                            "kind": "join",
                            "to_model": "sites",
                            "to_column": "SITE_ID",
                            "cardinality": "many_to_one",
                        },
                    ]
                },
            ),
            # SUBJECT_ID → cross-DP FK to the subject spine.
            # grain + MANY_TO_ONE join to subjects; FK lineage edge preserved.
            "SUBJECT_ID": _annotate(
                attribute(int64(), "SUBJECT_ID").referencing(
                    data_product="pharma-subjects-demo",
                    model="subjects",
                    attribute=["SUBJECT_ID"],
                ),
                {
                    "roles": [
                        {"kind": "grain"},
                        {
                            "kind": "join",
                            "to_model": "subjects",
                            "to_column": "SUBJECT_ID",
                            "cardinality": "many_to_one",
                            # CROSS-DP edge: subjects is owned by another DP and is
                            # NOT declared here. The owner label makes the kernel's
                            # referential check skip the local-model requirement so
                            # this join survives compile and reaches the harvest;
                            # the mesh resolves subjects at query time by its
                            # globally-unique bare model name.
                            "to_data_product": "pharma-subjects-demo",
                        },
                    ]
                },
            ),
        }
    )
    # Glossary links — model-level + attribute-level (by attr name). These render
    # in the discover UI glossary column.
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/site")
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/subject")
    .link("SITE_ID", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/site")
    .link("SUBJECT_ID", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/subject")
)

# ---------------------------------------------------------------------------
# Marker model — satisfies the storage port's produce-verification requirement.
# A tiny one-row table the transform writes via full_table_name("sites_smoke_marker").
# ---------------------------------------------------------------------------

provision_marker = (
    semantic_model("sites_smoke_marker")
    .description("Marker table written by the provisioning transform.")
    .schema(
        {
            "MARKER_ID": int64(),
            "VIEW_NAME": string(),
        }
    )
)
