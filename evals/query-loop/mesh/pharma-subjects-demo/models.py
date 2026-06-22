"""Models for pharma-subjects-demo — the SUBJECT SPINE of the mesh.

The transform seeds the real ``SUBJECTS`` table; we promise that REAL model on the
storage port (not a dummy marker), so the discover UI surfaces the actual
attributes, their glossary links, and (on downstream facts) the cross-DP
SEMANTIC RELATIONSHIP. ``subjects`` is the spine, so it has no outgoing cross-DP
reference; its attributes link to glossary terms.
"""

from nxd.spec import Predicate, attribute, semantic_model
from nxd.spec.data_types import int64, string

# The real subject-spine model the transform seeds (table SUBJECTS).
subjects_model = (
    semantic_model("subjects")
    .description("Subject spine — one row per enrolled clinical-trial subject.")
    .schema(
        {
            "SUBJECT_ID": int64(),
            "SUBJECT_COUNTRY": string(),
            # PII: medical record number.
            "SUBJECT_MRN": string(),
        }
    )
    # Glossary links at the model + attribute level (render in the UI).
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/subject")
    .link("SUBJECT_COUNTRY", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/subject_country")
)
