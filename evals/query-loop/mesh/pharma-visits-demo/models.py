"""Models for the pharma-visits (DP_VISITS) semantic-layer data product.

The transform seeds the real ``VISITS`` fact table; we promise that REAL model on
the storage port (not a dummy marker), so the discover UI surfaces the actual
attributes, their glossary links, and the cross-DP SEMANTIC RELATIONSHIP. The
``visits`` fact carries an outgoing cross-DP reference on SUBJECT_ID into the
subject spine (owned by pharma-subjects-demo); its attributes link to glossary
terms.
"""

from nxd.spec import Predicate, attribute, semantic_model
from nxd.spec.data_types import float64, int64, string

# The real visits-fact model the transform seeds (table VISITS). One row per
# clinical visit; MANY visits per subject.
visits_model = (
    semantic_model("visits")
    .description("One row per clinical visit. MANY visits per subject.")
    .schema(
        {
            "VISIT_ID": int64(),
            # Cross-DP FK into the subject spine (owned by pharma-subjects-demo).
            "SUBJECT_ID": attribute(int64(), "SUBJECT_ID").referencing(
                data_product="pharma-subjects-demo",
                model="subjects",
                attribute=["SUBJECT_ID"],
            ),
            "VISIT_TYPE": string(),
            "DURATION_MIN": float64(),
        }
    )
    # Glossary links at the model + attribute level (render in the UI).
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/visit")
    .link("VISIT_TYPE", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/visit")
    .link("SUBJECT_ID", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/subject")
)
