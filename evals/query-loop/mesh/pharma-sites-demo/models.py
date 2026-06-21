"""Models for DP_SITES (pharma-sites-demo).

With the SELF-SEED deploy pattern the base query tables (SITE_SUBJECTS, SITES)
are created AND populated by the ``.transform(...)`` in this DP's OWN Snowflake
schema (CREATE TABLE + INSERT), which then provisions the single-table semantic
view over them. The storage output port still needs at least one promised model,
and the transform needs the Snowflake connection that port supplies. So we
promise ONE tiny marker model that the transform creates — this satisfies the
port + produce-verification without promising the query tables themselves
(whose shape the semantic view, not the kernel, owns).
"""

from nxd.spec import semantic_model
from nxd.spec.data_types import int64, string

provision_marker = (
    semantic_model("site_provision_marker")
    .description("Marker table written by the self-seeding transform.")
    .schema(
        {
            "MARKER_ID": int64(),
            "VIEW_NAME": string(),
        }
    )
)
