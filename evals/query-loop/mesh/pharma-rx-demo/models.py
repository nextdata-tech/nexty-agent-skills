"""Models for the pharma-rx-demo (DP_RX) semantic-layer data product.

A storage output port requires at least one promised model. With the SELF-SEED
deploy pattern the base ``DISPENSES`` table and its single-table
``DISPENSES_SEMANTIC`` view are created AND populated by the ``.transform(...)``
in this DP's OWN Snowflake schema (CREATE TABLE + INSERT) — NOT materialised
via a facade.

We promise ONE tiny marker model that the transform creates. This satisfies the
port + produce-verification without promising the query tables (whose shape the
semantic view, not the kernel, owns).
"""

from nxd.spec import semantic_model
from nxd.spec.data_types import int64, string

# Marker model — produced by the transform, satisfies the storage port.
provision_marker = (
    semantic_model("pharma_rx_marker")
    .description("Marker table written by the self-seeding transform.")
    .schema(
        {
            "MARKER_ID": int64(),
            "VIEW_NAME": string(),
        }
    )
)
