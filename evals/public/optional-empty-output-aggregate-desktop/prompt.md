# Optional empty output and aggregate-only desktop product

The workspace contains a small synthetic order export under `data/` and a
brief describing a mapper-backed product. Build the complete Python-only
desktop closure at the workspace root using the installed Nexty skills.

The product has one required physical model, `orders`, and one optional
human-review physical model, `reviews`. The review export is intentionally
absent because this run has no review rows. Do not create a placeholder review
row or table. The product must still expose a catalog entry for `reviews`.

Expose an aggregate-only governed surface over `orders`: a semantic view with a
`COUNT(*)` metric and the supplied product-category dimension. The query result
must contain only category and count columns; do not expose order identifiers,
source text, or record-level rows through the acceptance query.

Use the public field-mapper seam described by the skill for the synthetic
mapper step. Keep all mapper input and output synthetic and local; do not use a
provider SDK, network access, or credentials. The mapper result may remain
run-local because this scenario evaluates the governed aggregate surface and
the optional review-output contract.

Do not hand-write `deployment-spec.yaml`, `manifest.yaml`, or `models.yaml`.
After authoring, run the compatible local supervisor with workflow
`mapper-aggregate-e2e`, require `published=yes`, call `describe` before the
governed grouped query, and stop the supervisor before finishing. Report only
the sanitized publication, catalog, and aggregate-query result.

Work autonomously. No user is available to answer a delivery question.
