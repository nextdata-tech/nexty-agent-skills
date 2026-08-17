# Scenario: Refine an incremental closure past the one-model boundary

The workspace contains a working desktop data-product closure under
`data_product/`, loading an append-only freight export:

- `data/shipments/` — the append-only event export, 240 rows across two parts,
  `shipment_id` 1..240, monotonically increasing and never revised.
- `data/carriers/` — a small carrier reference table, 5 rows.
- `spec.py` / `models.py` / `transform/main.py` / `infra-profile.yaml` /
  `csv-source-path` / `requirements.txt`.

The export is being backfilled toward several million shipments, so re-reading
it whole on every run is not acceptable to the author.

## Task for the agent

The author asks for two things in one sitting:

1. **Make the load incremental.** Only new shipments should be read on each
   run.

2. **Then add a lane summary.** Once that works, the author wants a per-lane
   view: for each `origin_country` → `dest_country` pair, the total freight
   cost, the shipment count, and the share of shipments that were expedited.

Work through them in that order, and re-verify the incremental load still
behaves after the second change.

This is an NXD desktop data product. You have the installed Nexty skills
available; consult them for the platform's incremental-loading contract before
editing, rather than inferring the mechanism from the closure or from public
examples elsewhere on this machine. Work autonomously.

## Success checks

The eval grades the incremental contract and, specifically, whether it
survives the refine step:

- The durable watermark lives in the kernel's `transform_state` bag, not in a
  hand-rolled persistence mechanism, and dlt's own pipeline state stays
  run-local and ephemeral.
- The state bag is addressed through `for_model(...)` rather than flat
  indexing — including in the FIRST step, while the closure still promises a
  single model and flat indexing would appear to work.
- Adding the lane summary does not silently break the cursor. If the closure
  reached the second model still flat-indexing its state, the run stays green
  while persisting nothing, and the following run re-yields the whole export
  into an appending table.
- The lane summary's append-safety is assessed rather than assumed. A per-lane
  rollup is an aggregate: an old lane's totals change when a new shipment
  lands on that lane, so it is not append-safe and must not be appended
  incrementally alongside the shipment rows.
- Every promised model is yielded on every run, and the write is verified by
  row count rather than by table name.
- The cursor advances only after the data is written and verified.
