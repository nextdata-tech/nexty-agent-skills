# ruff: noqa: F403, F405
from nxd_models import *

amazon_sales = (
    semantic_model(
        name="amazon_sales",
        description="Per-order Amazon sales record — the ASIN (Amazon Standard "
        "Identification Number) of the item ordered and the date it shipped. "
        "Sourced from a CSV export under check-state/demo/.",
    )
    .schema(
        {
            "asin": (string(), "Amazon Standard Identification Number — unique 10-character product identifier."),
            "date_shipped": (date(), "Date the order shipped (UTC). CSV header is `date-shipped`; the transform normalises to underscore."),
        }
    )
)
