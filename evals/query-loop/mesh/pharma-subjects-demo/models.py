"""Models for the pharma-subjects-demo semantic-layer data product.

This DP self-seeds its OWN base table (``SUBJECTS``) in its own Snowflake schema
via the transform (the template SELF-SEED pattern — NOT the facade), then
provisions a single-table ``SUBJECTS_SEMANTIC`` view over it.

A storage output port requires at least one promised model, and the transform
needs the Snowflake connection that port supplies. So we promise ONE tiny marker
model the transform creates — this satisfies the port + produce-verification
without promising the seeded base table (whose shape the semantic view, not the
kernel, owns).
"""

from nxd.spec import semantic_model
from nxd.spec.data_types import int64, string

provision_marker = (
    semantic_model("subjects_marker")
    .description("Marker table written by the provisioning transform.")
    .schema(
        {
            "MARKER_ID": int64(),
            "VIEW_NAME": string(),
        }
    )
)
