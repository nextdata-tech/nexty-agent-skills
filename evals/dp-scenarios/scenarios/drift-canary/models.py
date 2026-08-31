"""Models exercising base fields, optional output, and semantic metrics."""

from nxd.spec import Agg, dimension, field, join, metric, metric_field, primary_key
from nxd.spec import semantic_model, semantic_view
from nxd.spec.data_types import boolean, number, string


customers = semantic_model("customers").description("One row per customer.").schema(
    {
        "customer_id": field(number(), primary_key()),
        "name": string(),
    }
)


orders = semantic_model("orders").description("One row per order.").schema(
    {
        "order_id": field(number(), primary_key()),
        "customer_id": field(number(), join(to="customers", to_column="customer_id")),
        "amount": number(),
        "status": field(string(), dimension(name="order_status", description="Order status.")),
    }
)

file_rows = semantic_model("file_rows").description("Rows from the JSONL file source.").schema(
    {
        "row_id": field(number(), primary_key()),
        "label": field(string(), dimension(description="The file row label.")),
    }
)

db_rows = semantic_model("db_rows").description("Rows from the database source.").schema(
    {
        "row_id": field(number(), primary_key()),
        "name": string(),
    }
)

api_events = semantic_model("api_events").description("Rows from the API source.").schema(
    {
        "event_id": field(number(), primary_key()),
        "active": field(boolean(), dimension(description="Whether the event is active.")),
    }
)

optional_zero = semantic_model("optional_zero").description("An optional output that may have zero rows.").schema(
    {
        "row_id": field(number(), primary_key()),
        "note": string(),
    }
)

event_metrics = semantic_view("event_metrics", orders).description("Question-driven order measures.").schema(
    {
        "order_amount": metric_field(
            number(),
            metric(
                Agg.SUM,
                of=orders.field("amount"),
                name="order_amount",
                description="Sum of order amounts.",
            ),
        )
    }
)
