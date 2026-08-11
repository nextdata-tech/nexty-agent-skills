# Labeled CSV closure brief

Build a local desktop data product named `labeled-orders-users` from two
separate CSV source exports. Keep the source rows unchanged and land one
physical model per source:

- label `orders`, model `orders`, keyed by `order_id`;
- label `users`, model `users`, keyed by `user_id`.

The `archive` export is present only to exercise the empty-source boundary. It
has no rows and is not part of the product's promised models. Do not invent
rows, a key, or a placeholder runtime input for it.

The transform must read the two labeled roots from the immutable closure it is
executed from, write through the local DuckDB output port, and publish the two
promised physical tables. No semantic view or API connector is needed.
