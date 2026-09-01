"""Synthetic order and review models for the desktop acceptance closure."""

from nxd.spec import (
    Agg,
    dimension,
    field,
    metric,
    metric_field,
    primary_key,
    semantic_model,
    semantic_view,
)
from nxd.spec.data_types import int64, string


orders = semantic_model("orders").description("Synthetic orders.").fields(
    {
        "ORDER_ID": field(string(), primary_key()),
        "PRODUCT_CATEGORY": field(
            string(),
            dimension(name="product_category", description="Order category."),
        ),
        "ORDER_TEXT": string(),
    }
)

reviews = semantic_model("reviews").description(
    "Optional human review rows."
).fields(
    {
        "REVIEW_ID": field(string(), primary_key()),
        "ORDER_ID": string(),
        "REVIEW_TEXT": string(),
    }
)

order_metrics = semantic_view("order_metrics", orders).description(
    "Aggregate-only governed metrics over orders."
).fields(
    {
        "ORDER_COUNT": metric_field(
            int64(),
            metric(Agg.COUNT, of=orders.field("*"), description="Number of orders."),
        )
    }
)
