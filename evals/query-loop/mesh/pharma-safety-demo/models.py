"""Models for pharma-safety-demo — the FAR ADVERSE-EVENTS FACT of the mesh.

The transform seeds the real ``ADVERSE_EVENTS`` table; we promise that REAL model
on the storage port (not a dummy marker), so the discover UI surfaces the actual
attributes, their glossary links, and the cross-DP SEMANTIC RELATIONSHIP
(SUBJECT_ID -> pharma-subjects-demo/subjects/SUBJECT_ID).
"""

from nxd.spec import Predicate, attribute, semantic_model
from nxd.spec.data_types import boolean, int64, string

# The real adverse-events fact the transform seeds (table ADVERSE_EVENTS).
# Grain AE_ID; one row per adverse event, MANY adverse events per subject.
adverse_events_model = (
    semantic_model("adverse_events")
    .description("Adverse-events fact — one row per adverse event (grain AE_ID).")
    .schema(
        {
            "AE_ID": int64(),
            # Cross-DP FK to the subject spine — fills the UI SEMANTIC
            # RELATIONSHIP column.
            "SUBJECT_ID": attribute(int64(), "SUBJECT_ID").referencing(
                data_product="pharma-subjects-demo",
                model="subjects",
                attribute=["SUBJECT_ID"],
            ),
            "AE_TERM": string(),
            "IS_SERIOUS": boolean(),
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
