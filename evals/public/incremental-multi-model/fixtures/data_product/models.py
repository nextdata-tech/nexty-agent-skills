"""Base models and query-time metrics for the freight-shipments desktop DP."""

from nxd.spec import Agg, semantic_model, semantic_view
from nxd.spec.data_types import number, string
from nxd.spec import dimension, field, metric, metric_field, primary_key

shipments = semantic_model("shipments").schema(
    {
        # Monotonically increasing per the append-only export.
        "shipment_id": field(number(), primary_key()),
        "carrier_id": field(string(), dimension(name="carrier")),
        "origin_country": field(string(), dimension(name="origin_country")),
        "dest_country": field(string(), dimension(name="dest_country")),
        "shipped_date": field(string(), dimension(name="shipped_date")),
        "weight_kg": number(),
        "freight_cost_eur": number(),
        "is_expedited": field(string(), dimension(name="is_expedited")),
    }
)

carriers = semantic_model("carriers").schema(
    {
        "carrier_id": field(string(), primary_key()),
        "carrier_name": field(string(), dimension(name="carrier_name")),
        "mode": field(string(), dimension(name="mode")),
    }
)

shipment_metrics = semantic_view("shipment_metrics", shipments).schema(
    {
        "total_freight_cost_eur": metric_field(
            number(),
            metric(
                Agg.SUM,
                of=shipments.field("freight_cost_eur"),
                name="total_freight_cost_eur",
            ),
        ),
        "total_weight_kg": metric_field(
            number(),
            metric(Agg.SUM, of=shipments.field("weight_kg"), name="total_weight_kg"),
        ),
    }
)
