"""Models for the pharma-labs (DP_LABS) semantic-layer data product.

The transform seeds this DP's OWN base table (``ASSAYS``) in its own Snowflake
schema (the TRANSFORM-SEED pattern), then provisions a single-table
``ASSAYS_SEMANTIC`` view over it.

We promise the REAL ``assays`` model on the storage port (not a dummy marker),
so the discover UI surfaces the actual attributes, their glossary links, and the
cross-DP SEMANTIC RELATIONSHIP. The ``SUBJECT_ID`` attribute `.referencing(...)`s
the subject spine (``subjects`` in pharma-subjects-demo), so the relationship is
declared + discoverable across the mesh. The cross-DP join itself resolves at
query time (the registry's MANY_TO_ONE join to the ``site_subjects`` crosswalk),
never in this DP's single-table view DDL.
"""

from nxd.spec import Predicate, attribute, semantic_model
from nxd.spec.data_types import float64, int64, string

# The real ASSAYS base table the transform seeds (grain ASSAY_ID, MANY assays per
# subject). Columns mirror the registry's `assays` model + the seeded DataFrame:
# the assay_type dimension, the titer measure, and the SUBJECT_ID join key into
# the subject spine. SUBJECT_ID declares the cross-DP FK to pharma-subjects-demo's
# `subjects.SUBJECT_ID` (fills the UI SEMANTIC RELATIONSHIP column).
assays_model = (
    semantic_model("assays")
    .description("Lab assays base table (one row per assay).")
    .schema(
        {
            "ASSAY_ID": int64(),
            "SUBJECT_ID": attribute(int64(), "SUBJECT_ID").referencing(
                data_product="pharma-subjects-demo",
                model="subjects",
                attribute=["SUBJECT_ID"],
            ),
            "ASSAY_TYPE": string(),
            "TITER": float64(),
        }
    )
    # Model-level glossary link + key attribute-level links (render in the UI).
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/assay")
    .link("TITER", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/titer")
    .link("SUBJECT_ID", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/subject")
)
