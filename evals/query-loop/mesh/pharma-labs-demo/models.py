"""Models for the pharma-labs (DP_LABS) semantic-layer data product.

This DP self-seeds its OWN base table (``ASSAYS``) in its own Snowflake schema
via the transform (the TRANSFORM-SEED pattern), then provisions a single-table
``ASSAYS_SEMANTIC`` view over it.

A storage output port requires at least one promised model, and the transform
needs the Snowflake connection that port supplies. So we promise ONE tiny marker
model the transform creates (``assays_marker``) — this satisfies the port +
produce-verification without promising the seeded base table (whose shape the
semantic view, not the kernel, owns).

The ``assays_model`` carries the real cross-DP FK: its ``SUBJECT_ID`` attribute
`.referencing(...)`s the subject spine (``subjects`` in pharma-subjects-demo), so
the relationship is declared + discoverable across the mesh. The cross-DP join
itself resolves at query time (the registry's MANY_TO_ONE join to the
``site_subjects`` crosswalk), never in this DP's single-table view DDL.
"""

from nxd.spec import attribute, semantic_model
from nxd.spec.data_types import float64, int64, string

provision_marker = (
    semantic_model("assays_marker")
    .description("Marker table written by the seeding transform.")
    .schema(
        {
            "MARKER_ID": int64(),
            "VIEW_NAME": string(),
        }
    )
)

# Descriptive model of the self-seeded ASSAYS base table. Columns mirror the
# registry's `assays` model: grain ASSAY_ID, the assay_type dimension, the titer
# measure, and the SUBJECT_ID join key into the subject spine. SUBJECT_ID
# declares the cross-DP FK to pharma-subjects-demo's `subjects.SUBJECT_ID`.
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
)
