"""Base models and query-time metrics for the storefront-events desktop DP."""

from nxd.spec import Agg, semantic_model, semantic_view
from nxd.spec.data_types import number, string
from nxd.spec import dimension, field, metric, metric_field, primary_key

events = semantic_model("events").schema(
    {
        # Monotonically increasing per the append-only export.
        "event_id": field(number(), primary_key()),
        "occurred_at": string(),
        "user_id": field(string(), dimension(name="user")),
        "event_type": field(string(), dimension(name="event_type")),
        "value_cents": number(),
    }
)

event_metrics = semantic_view("event_metrics", events).schema(
    {
        "total_value_cents": metric_field(
            number(),
            metric(Agg.SUM, of=events.field("value_cents"), name="total_value_cents"),
        ),
    }
)
