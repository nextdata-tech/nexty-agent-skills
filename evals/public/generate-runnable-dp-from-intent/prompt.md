# Scenario: Generate a Runnable Data Product from Intent

This scenario measures the code-generation half of the AI data-product flow: the semantic model has ALREADY been inferred (the nxd-semantic-data-product skill's inference mode ran in a previous step and left `inferred_model.json` in the workspace), and the connector data is already exported. The agent must assemble the **complete runnable definition closure** around those inputs — `spec.py`, `models.py`, `transform/main.py`, `requirements.txt`, and the `deployment-spec.yaml` / `manifest.yaml` / `models.yaml` / `csv-source-path` wiring — in exactly the shape the lean-desktop (S0) supervisor pins, boots, and publishes.

The correctness spine is the **naming invariant**: `.model(name)` == the `models.yaml` model name == the `manifest.yaml` `model_tables` key AND value == the `data/<name>/` connector subdirectory == the physical table dlt writes, `main.<name>`, unquoted lowercase. dlt lowercases/snake_cases whatever it is given, so the generated transform must read back the produced table names and assert they match the promise. The transform must ingest **through the DuckDB output port handle** (dlt destination on `output.path` / `output.schema`) — not via direct `duckdb.connect` writes, not via view DDL — with the connector root arriving in `secrets["csv_source"]` and the manifest carrying the verbatim `__NXD_STAGING_DATA__` staging placeholder the supervisor substitutes at snapshot time.

The skill being evaluated (`nxd-generate-dp`, NEX-783) teaches the closure layout, the proven dlt-through-port transform shape, the S0 driver ids and wiring, the proven dependency pins, and the naming-invariant self-check. The shipped acceptance test executes the generated transform for real (nxd stubbed, dlt live) and verifies the produced DuckDB.

## Task for the agent

Your team's agent pipeline has already done the analysis half of this job; you do the assembly half.

### The intent

> "We get a nightly CSV export from our commerce platform — one folder per table, currently `customers` and `orders`. Build me a data product I can run locally on the desktop supervisor so our AI assistant can answer questions like *total revenue by sales channel*, *churned customers per segment*, *which countries place the most orders*, and *average order value* over governed semantic tools."

### Inputs in your workspace

- `inferred_model.json` — the inferred semantic model handed off by the semantic-inference step: per model, a description plus per-column `data_type` and the ready `__nxd_semantic__` role blobs. **Place these blobs verbatim** — the inference step already designed them (grains, metrics, dimensions, join, PII flags); do not redesign, rename, add, or drop roles.
- `data/` — the connector export: `data/customers/customers.csv` and `data/orders/orders.csv`, one subdirectory per table. This directory is part of the closure (the CSV source the transform ingests).
- `check_generated_closure.py` — the shipped acceptance test (do not edit it).

### What to do

1. Read `inferred_model.json` and the CSV headers under `data/` before writing anything — the model names, column vocabulary, and types all come from those inputs.
2. Generate the complete closure at the workspace root: `spec.py`, `models.py`, `transform/main.py`, `requirements.txt`, `deployment-spec.yaml`, `manifest.yaml`, `models.yaml`, and `csv-source-path` (pointing at `data`). The closure must be runnable by the desktop supervisor as-is: exact S0 driver ids, the verbatim staging placeholder, the dlt-through-port transform with the read-back-and-assert naming check and the `.transform-complete` readiness marker, and the proven dependency pins.
3. Verify the closure with the shipped acceptance test — it statically validates the wiring consistency and then actually EXECUTES your transform against `data/` into a scratch DuckDB:

   ```
   uv run --python 3.12 --with "dlt[duckdb]==1.28.2" --with "duckdb==1.5.4" \
       --with "pandas==2.3.3" --with pyyaml python check_generated_closure.py
   ```

   It must print `ALL CHECKS PASSED`. If it fails, fix the closure and re-run; do not finish with a failing check, and do not edit the acceptance test itself.
4. In your final answer include: (a) the closure file inventory, (b) `transform/main.py` verbatim, (c) the model→table mapping and a short confirmation of where each of the five naming-invariant surfaces agrees (models.py / models.yaml / model_tables / data subdirs / the physical `main.<name>` tables), and (d) the acceptance-test result.

## Required artifacts from eval runner

- `fixtures/data/` — the committed deterministic CSV connector export (copied into the agent workspace; also serves as the closure's `data/` directory).
- `fixtures/inferred_model.json` — the inferred-model handoff (copied into the agent workspace).
- `fixtures/check_generated_closure.py` — the acceptance test (copied into the agent workspace). It stubs the nxd API (spec surface, transform runtime, `DuckDbOutput`), so no nxd wheel is needed; it requires `dlt[duckdb]==1.28.2`, `duckdb==1.5.4`, `pandas`, and `pyyaml`, obtainable via `uv run` as shown in the task.
- `uv` (or an equivalent way to obtain the pinned packages) available in the workspace.
- No S0 supervisor/kernel is available in the eval environment — validation is the shipped acceptance test, which mirrors the supervisor's execution contract (typed `DuckDbOutput` handle, `csv_source` secret, staging file + `.transform-complete` readiness gate) without booting it.

## Note on the annotation stopgap

The public per-field author API (`AttributeSpec.semantic_annotation()`) is not yet merged; the semantic skill documents a clearly-marked stopgap that injects the `__nxd_semantic__` blob into `AttributeSpec._metadata` via a small `_annotate()` helper. Using that documented stopgap in `models.py` is correct for this scenario (the acceptance test accepts both the stopgap and the public setter).
