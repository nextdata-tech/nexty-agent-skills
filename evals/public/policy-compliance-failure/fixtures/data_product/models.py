# ruff: noqa: F403, F405
from nxd_models import *

# Input model: raw order events landed from the orders service.
orders_raw_model = (
    semantic_model("orders_raw_model")
    .description("Raw order events ingested from the orders service")
    .schema(
        {
            "order_id": (string(), "Source order identifier"),
            "customer_id": (string(), "Customer who placed the order"),
            "status": (string(), "Lifecycle status of the order"),
            "amount": (number(), "Order total in minor currency units"),
            "created_at": (
                timestamp(unit=DurationUnit.Milliseconds, timezone=None),
                "When the order was created",
            ),
        }
    )
)

# Output model: curated, deduplicated orders published for downstream consumers.
orders_curated_model = (
    semantic_model("orders_curated_model")
    .description("Curated orders with normalized status, published for consumers")
    .schema(
        {
            "order_id": (string(), "Unique curated order identifier"),
            "customer_id": (string(), "Customer who placed the order"),
            "status": (string(), "Normalized order status"),
            "amount": (number(), "Order total in minor currency units"),
            "created_at": (
                timestamp(unit=DurationUnit.Milliseconds, timezone=None),
                "When the order was created",
            ),
        }
    )
)
