"""Marker model for the cross-DP query facade DP.

This DP owns no real data — it serves the ``run_cross_dp_query`` MCP tool, which
reads OTHER DPs' schemas. But the nxd validator requires every output port to
promise at least one model, so we promise a tiny MARKER model: a single-column
table the no-op transform creates and seeds with one row. It exists only to
satisfy the output-port promise + its post-transform verification; nothing reads
it. (See overview.md — "one promised marker model".)
"""

from nxd.spec import semantic_model
from nxd.spec.data_types import string

# Tiny marker — one column, one row. Not part of any query; only satisfies the
# output-port promise contract.
marker_model = (
    semantic_model("cross_dp_query_marker")
    .description(
        "Marker model for the cross-DP query facade. Carries no business data — "
        "the DP serves the run_cross_dp_query tool, which reads other DPs' schemas."
    )
    .schema({"MARKER": string()})
)
