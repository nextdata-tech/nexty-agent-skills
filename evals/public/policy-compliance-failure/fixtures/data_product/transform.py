"""Curate raw order events: dedupe by order_id and normalize status."""


def transform(orders, ctx):
    seen = set()
    rows = []
    for order in orders:
        order_id = order["order_id"]
        if order_id in seen:
            continue
        seen.add(order_id)
        rows.append(
            {
                "order_id": order_id,
                "customer_id": order["customer_id"],
                "status": (order["status"] or "").strip().lower(),
                "amount": order["amount"],
                "created_at": order["created_at"],
            }
        )
    return rows
