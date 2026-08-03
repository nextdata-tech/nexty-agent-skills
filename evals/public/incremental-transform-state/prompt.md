# Scenario: Incremental Load of an Append-Only Source on Pocket

The workspace contains a working Pocket data-product closure under
`data_product/`, built by the default nxd-generate-data-product path:

- `spec.py` / `models.py` — promises one physical model, `events`, on the
  `duckdb` port, plus an `event_metrics` view.
- `transform/main.py` — reads the CSV export through dlt and lands `events` with
  `pipeline.run(resources, write_disposition="replace")`, with dlt's
  `pipelines_dir` and `DLT_DATA_DIR` set under the run directory.
- `data/events/` — the source export (100 rows, `event_id` 1..100).
- `infra-profile.yaml`, `csv-source-path`, `requirements.txt`.

`nxd-run-history.txt` holds the row counts from the two runs so far (stable at
100, since replace is idempotent) and the author's note about the source.

The source is an append-only event export. Files only ever gain rows, nothing
already written is revised or deleted, and every row carries a monotonically
increasing `event_id`. The export is being backfilled toward several million
rows, so re-reading it whole on every run is no longer acceptable to the author.

Task for the agent:

The author asks: "this re-reads the entire export every time — can you make it
load only the new events?" Make the change in `data_product/`.

This is an NXD Pocket data product. You have the installed Nexty skills
available; consult them for the platform's incremental-loading contract before
editing, rather than inferring the mechanism from the closure or from public
examples elsewhere on this machine. Work autonomously.

Success checks:

- The agent uses the kernel's `transform_state` kwarg to hold the durable
  watermark, rather than inventing its own persistence.
- The agent keeps dlt's own pipeline state run-local and ephemeral — it does NOT
  move `pipelines_dir` / `DLT_DATA_DIR` outside the run directory or to `~/.dlt`
  in order to make dlt's incremental cursor survive between runs.
- The agent switches the landing disposition to `write_disposition="append"` and
  does NOT leave `write_disposition="replace"` in place while yielding only the
  new rows.
- The agent confirms the promised model is append-safe before appending, rather
  than assuming an append-only source makes every output model append-safe.
- The agent advances the cursor only after the data has been written and
  verified, and does not rely on a raise rolling back rows already written.
- The agent verifies the append in a way that can actually detect a model that
  was not written, rather than trusting the table-name assert alone.
- The agent handles the first run, where the state bag is empty, by defaulting to
  a value that takes the whole history rather than skipping it.
- The agent stores a JSON-serializable cursor value.
- The agent addresses the state bag in a form that keeps working when the closure
  promises more than one model.
- The agent's read-back code, if any, works despite the `duckdb` port parameter
  shadowing the `duckdb` module, and survives the first run when no DuckDB file
  exists yet.
- The agent does NOT propose a `.when(...)` per-model DAG on desktop, and does not
  reference the Databricks-only transform-state sidecar env var.
- The agent preserves the rest of the transform contract: typed `DuckDbOutput`,
  source config from `secrets`, writes through the port, and the
  `.transform-complete` touch.
