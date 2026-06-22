"""Models for DP_SITES (pharma-sites-demo) — the MANY_TO_MANY crosswalk HUB.

The transform seeds the REAL ``SITE_SUBJECTS`` crosswalk table; we promise that
REAL model on the storage port (not a dummy marker), so the discover UI surfaces
the actual attributes, their glossary links, and the cross-DP SEMANTIC
RELATIONSHIP. ``site_subjects`` is the fan-out hub: SUBJECT_ID references the
subject spine (pharma-subjects-demo/subjects) and SITE_ID references the site
dimension (this DP's own ``sites``).
"""

from nxd.spec import Predicate, attribute, semantic_model
from nxd.spec.data_types import int64

# The real crosswalk-hub model the transform seeds (table SITE_SUBJECTS).
# Attributes carry cross-DP FK references (.referencing → UI "SEMANTIC
# RELATIONSHIP"); glossary links are attached at the model level by attr name.
site_subjects_model = (
    semantic_model("site_subjects")
    .description(
        "Crosswalk hub — one row per (site, subject) enrollment, "
        "MANY_TO_MANY fan-out linking the subject spine to the site dimension."
    )
    .schema(
        {
            # SITE_ID → this DP's own sites dimension.
            "SITE_ID": attribute(int64(), "SITE_ID").referencing(
                data_product="pharma-sites-demo", model="sites", attribute=["SITE_ID"]
            ),
            # SUBJECT_ID → cross-DP FK to the subject spine.
            "SUBJECT_ID": attribute(int64(), "SUBJECT_ID").referencing(
                data_product="pharma-subjects-demo",
                model="subjects",
                attribute=["SUBJECT_ID"],
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
