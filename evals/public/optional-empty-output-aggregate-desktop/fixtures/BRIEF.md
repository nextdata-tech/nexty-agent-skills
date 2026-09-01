# Synthetic mapper aggregate product

The source is a synthetic order export. Each row has a stable `order_id`, a
`product_category`, and source text from which a local mapper can recover the
category. The product is aggregate-only: consumers need the governed number of
orders by category, not order identifiers or source text.

The human-review output is a valid part of the product contract, but this
fixture has no review rows yet. A zero-row review resource may be absent
physically. It must remain visible in the semantic catalog and must not be
replaced with a fake row or a fabricated count.
