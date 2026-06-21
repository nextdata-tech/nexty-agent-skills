"""Promised model for the pharma-safety (DP_SAFETY) semantic-layer data product.

SELF-SEED deploy pattern (MESH_DESIGN.md): the transform creates this DP's own
base table (``ADVERSE_EVENTS``) + a single-table ``ADVERSE_EVENTS_SEMANTIC``
view in the DP's Snowflake schema, and writes a one-row marker table that is the
single promised output model.

A storage output port requires at least one promised model. We promise ONLY the
marker (not the query tables themselves), so produce-verification passes without
the kernel owning the shape of the semantic tables (the registry owns that).
"""

from nxd.spec import semantic_model
from nxd.spec.data_types import int64, string

# Marker model — written by the self-seed transform, satisfies the storage port
# + the produce-verification without promising the query tables.
provision_marker = (
    semantic_model("pharma_safety_marker")
    .description("Marker table written by the self-seed transform.")
    .schema(
        {
            "MARKER_ID": int64(),
            "VIEW_NAME": string(),
        }
    )
)
