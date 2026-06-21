"""Models for the pharma-visits (DP_VISITS) semantic-layer data product.

SELF-SEED pattern (like the deployable-dp template): the transform creates and
populates this DP's OWN base table (``visits`` fact) in this DP's own Snowflake
schema, then hand-authors a single-table ``VISITS_SEMANTIC`` view over it.

A storage output port requires at least one promised model, and the transform
needs the Snowflake connection that port supplies. So we promise ONE tiny marker
model the transform actually creates — this satisfies the port +
produce-verification without promising the seeded fact table itself (whose shape
the semantic view, not the kernel, owns).
"""

from nxd.spec import semantic_model
from nxd.spec.data_types import int64, string

# Marker model — produced by the transform, satisfies the storage output port.
provision_marker = (
    semantic_model("pharma_visits_marker")
    .description("Marker table written by the provisioning transform.")
    .schema(
        {
            "MARKER_ID": int64(),
            "VIEW_NAME": string(),
        }
    )
)
