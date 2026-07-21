# `models.py` worked example

Matches the proven closure referenced by `SKILL.md` Step 3 — a full
`models.py` showing base models with placed roles plus one semantic view with
a metric. Use it as the concrete shape to match; do not deviate from the
`primary_key()` / `dimension(...)` / `join(...)` / `metric_field(metric(...))`
DSL calls shown here.

```python
"""Base models and query-time metrics for the desktop DP."""

from nxd.spec import Agg, semantic_model, semantic_view
from nxd.spec.data_types import number, string
from nxd.spec import dimension, field, join, metric, metric_field, primary_key

customers = semantic_model("customers").schema(
    {
        "customer_id": field(number(), primary_key()),
        "country_id": field(
            string(),
            dimension(name="customer_country"),
        ),
        "country": string(),
    }
)

orders = semantic_model("orders").schema(
    {
        "order_id": field(number(), primary_key()),
        "customer_id": field(
            number(),
            join(to="customers", to_column="customer_id"),
        ),
        "amount": number(),
    }
)

order_metrics = semantic_view("order_metrics", orders).schema(
    {
        "total_order_amount": metric_field(
            number(),
            metric(Agg.SUM, of=orders.field("amount"), name="total_order_amount"),
        ),
    }
)
```
