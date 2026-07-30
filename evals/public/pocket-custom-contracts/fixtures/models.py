"""Supplied semantic model for the Pocket custom-contracts scenario."""
from nxd.spec import dimension, field, primary_key, semantic_model
from nxd.spec.data_types import decimal, string

orders = semantic_model("orders").description("One order line from the supplied export.").schema({
    "line_id": field(string(), primary_key()),
    "order_id": field(string(), dimension(description="Order containing this line.")),
    "currency": field(string(), dimension(description="Order currency.")),
    "order_total": field(decimal(18, 2), dimension(description="Reported order total.")),
    "line_total": field(decimal(18, 2), dimension(description="Amount for this order line.")),
})
