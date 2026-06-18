# ruff: noqa: F403, F405
from nxd_models import *

# Input: raw inventory snapshots pulled from the store point-of-sale export.
inventory_snapshot_model = (
    semantic_model("inventory_snapshot_model")
    .description("Per-store, per-SKU inventory snapshot exported from the POS")
    .schema(
        {
            "store_id": (string(), "Stable identifier for the retail store"),
            "sku": (string(), "Stock keeping unit identifier"),
            "on_hand": (number(), "Units physically on hand at snapshot time"),
            "snapshot_at": (
                timestamp(unit=DurationUnit.Milliseconds, timezone=None),
                "Time the snapshot was taken",
            ),
        }
    )
)

# Output: daily availability rollup per store and SKU.
availability_model = (
    semantic_model("availability_model")
    .description("Daily inventory availability per store and SKU")
    .schema(
        {
            "store_id": (string(), "Stable identifier for the retail store"),
            "sku": (string(), "Stock keeping unit identifier"),
            "available_units": (number(), "Units available for sale"),
            "in_stock": (boolean(), "Whether the SKU is currently in stock"),
            "as_of": (
                timestamp(unit=DurationUnit.Milliseconds, timezone=None),
                "Date the availability was computed for",
            ),
        }
    )
)
