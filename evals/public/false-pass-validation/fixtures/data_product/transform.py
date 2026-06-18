"""Roll POS inventory snapshots up into a daily per-store availability table."""

from datetime import timezone


def transform(snapshots, ctx):
    """Reduce raw snapshots to one availability row per (store_id, sku)."""
    latest = {}
    for row in snapshots:
        key = (row["store_id"], row["sku"])
        current = latest.get(key)
        if current is None or row["snapshot_at"] > current["snapshot_at"]:
            latest[key] = row

    rows = []
    for (store_id, sku), snap in latest.items():
        available = max(int(snap["on_hand"]), 0)
        rows.append(
            {
                "store_id": store_id,
                "sku": sku,
                "available_units": available,
                "in_stock": available > 0,
                "as_of": snap["snapshot_at"].astimezone(timezone.utc),
            }
        )
    return rows
