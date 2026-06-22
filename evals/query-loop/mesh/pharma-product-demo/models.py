"""Models for the DP_PRODUCT semantic-layer data product (self-seeded).

This DP self-seeds its OWN `products` base table in its own Snowflake schema (the
transform runs CREATE TABLE + INSERT), then provisions a single-table
`PRODUCTS_SEMANTIC` view over it. No facade, no provision-time view DDL.

A storage output port requires at least one promised model, and the transform
needs the Snowflake connection that port supplies. So we promise ONE tiny marker
model that the transform actually creates — this satisfies the port +
produce-verification without promising the seeded query table itself (whose shape
the semantic view, not the kernel, owns).

`products_model` is kept only as the schema descriptor the registry/tools and the
hand-authored single-table view reference; it is NOT the promised output.
"""

from nxd.spec import semantic_model
from nxd.spec.data_types import int64, string

# Schema descriptor for the self-seeded `products` base table (not promised).
products_model = (
    semantic_model("products")
    .description("Product dimension table self-seeded by the transform.")
    .schema(
        {
            "PRODUCT_ID": int64(),
            "PRODUCT_NAME": string(),
            "MODALITY": string(),
        }
    )
)

# Marker model — produced by the transform, satisfies the storage output port.
provision_marker = (
    semantic_model("pharma_product_marker")
    .description("Marker table written by the self-seeding transform.")
    .schema(
        {
            "MARKER_ID": int64(),
            "VIEW_NAME": string(),
        }
    )
)
