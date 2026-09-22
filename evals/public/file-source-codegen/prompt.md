# Scenario: Generate a local file data-product source

The workspace contains `source-contract.yaml`, a pinned local contract for
three tabular models. It deliberately exercises the three non-CSV formats in
the installed file-source recipe: JSONL, a plain JSON array, and Parquet. The
eval is local-only: do not contact a provider or install dependencies.

## Task

Read `source-contract.yaml` before authoring. Create a Python-only local
desktop data-product closure at the workspace root with:

- `spec.py`
- `models.py`
- `infra-profile.yaml`
- `transform/main.py`
- `file-source-path`
- `requirements.txt`
- `README.md`

Use the `file-source` recipe from the installed `nxd-generate-data-product`
skill. Keep the supplied model roots and file bytes unchanged. Detect the
format per model directory and use dlt's filesystem reader with `read_jsonl`
for JSONL and `read_parquet` for Parquet. Plain JSON is a single array/object
and needs the small custom dlt resource described by the recipe; do not pass it
to the JSONL reader. Every resource must be renamed to the declared physical
model name and landed through the local DuckDB pipeline.

The source is non-secret local topology. Use a relative `file-source-path`,
keep the `file-source` service free of credential attributes, and do not create
an API probe, HTTP client, network call, or deployment manifest. Do not run dlt
or install dependencies; a static syntax check is sufficient.

## Eval boundary

The evaluator checks the generated closure statically. It does not provide a
supervisor, execute the transform, or contact any external service.
