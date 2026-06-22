"""Promised model for the pharma-labs (DP_LABS) semantic-layer data product.

A storage output port requires at least one promised model. With the SELF-SEED
deploy pattern (MESH_DESIGN.md) the base table ``ASSAYS`` is created AND
populated by the transform in this DP's OWN Snowflake schema, and the port
promises that table so produce-verification passes.
"""

from nxd.spec import semantic_model
from nxd.spec.data_types import float64, int64, string

# The self-seeded base table the storage port promises. Columns mirror the
# registry's model: grain ASSAY_ID, the assay_type dimension, the titer measure,
# and the SUBJECT_ID join key into the crosswalk hub (join resolves at query
# time across the mesh; this DP's own view is single-table).
assays_model = (
    semantic_model("assays")
    .description("Lab assays base table (one row per assay).")
    .schema(
        {
            "ASSAY_ID": int64(),
            "SUBJECT_ID": int64(),
            "ASSAY_TYPE": string(),
            "TITER": float64(),
        }
    )
)
