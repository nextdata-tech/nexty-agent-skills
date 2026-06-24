"""Marker model for the cross-DP query facade DP.

This DP owns no real data — it serves the ``run_cross_dp_query`` MCP tool, which
reads OTHER DPs' schemas. But the nxd validator requires every output port to
DECLARE at least one model, so we declare a tiny MARKER model via ``.model(...)``
on the storage port (see spec.py). ``.model()`` declares the model WITHOUT a
production/verification contract — so there is no transform and nothing is
seeded; the marker exists only to satisfy the every-port-needs-a-model rule.
Nothing reads it.
"""

from nxd.spec import semantic_model
from nxd.spec.data_types import string

# Tiny marker — a single declared column. Not part of any query; only satisfies
# the validator's every-port-needs-a-model rule (declared, not produced).
marker_model = (
    semantic_model("cross_dp_query_marker")
    .description(
        "Marker model for the cross-DP query facade. Carries no business data — "
        "the DP serves the run_cross_dp_query tool, which reads other DPs' schemas."
    )
    .schema({"MARKER": string()})
)
