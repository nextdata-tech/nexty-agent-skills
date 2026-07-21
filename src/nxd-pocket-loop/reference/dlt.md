# DLT Data Product Authoring

Data Load Tool (dlt) is used to author pocket loop transformation functions. The source and documentation is
available at https://github.com/dlt-hub/dlt/archive/refs/tags/VERSION.tar.gz (substitute the actual dlt release
tag for `VERSION`).

The closure ships its own `infra-profile.yaml` with three services — `duckdb` (local DuckDB storage, the output
port backend), `python-compute` (runs the transform), and the connector service (see below). The storage output
port and the transform's typed parameter **MUST both be named `duckdb`**, not `output` — the local DuckDB driver
requires that exact name. This gives a transform signature like:
```python
@data_product.on_transform()
def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any]) -> None:
    ...
```
The `secrets` dictionary should contain the values required to construct the various dlt inputs. The `secrets`
dictionary is populated by the `secrets` element of the data product spec. The data product should populate
this with the required connector information provided by the user; nxd-generate-dp owns the exact infra-profile
service/secrets shape (see below) — do not construct an ad hoc infra profile of your own.

The `secrets` dict key and the generic-secrets service name are connector-type-specific: `csv_source`/`csv-source`
(CSV file), `file_source`/`file-source` (JSON/JSONL/Parquet file), `db_source`/`db-source` (live database),
`api_source`/`api-source` (off-mesh REST API). These names are for exactly one source of that type; when a data
product needs two or more (same or mixed types), each gets a label and the keys/names become
`<type>_source_<label>`/`<type>-source-<label>` — see nxd-generate-dp's `reference/multi-source.md`. See
nxd-generate-dp's `reference/` directory for the exact per-type secrets shape and transform wiring.
