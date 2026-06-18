# Service Inspection Recipes

Read-only inspection recipes, **one per service type** — mirroring the `scripts/drivers/` plugins. Each recipe maps an infra profile service's `attributes` to connection parameters and lists the metadata to collect.

## Per-service-type recipes

| Service type | Recipe | Driver plugin |
|---|---|---|
| S3 | `services/s3.md` | `drivers/s3.py` ✓ |
| ADLS | `services/adls.md` | `drivers/adls.py` ✓ |
| Snowflake | `services/snowflake.md` | `drivers/snowflake.py` ✓ |
| Databricks storage | `services/databricks-storage.md` | recipe only |
| BigQuery | `services/bigquery.md` | recipe only |
| Postgres / pgvector | `services/postgres.md` | recipe only |
| Kafka | `services/kafka.md` | recipe only |
| Pinecone | `services/pinecone.md` | recipe only |
| API | `services/api.md` | recipe only |

✓ means a driver plugin already implements the recipe. For the rest, the recipe **is** the spec — build `scripts/drivers/<name>.py` from it and add it to `ALL` in `drivers/__init__.py`.

Other SQL / object stores not listed: `redshift` inspects like Postgres; `minio` like S3 with a custom `endpoint_url`; `dremio` / `duckdb` over SQL (`SHOW TABLES` / `DESCRIBE`). For an unknown driver, ask the user for connection details rather than guessing.

## General pattern

A driver's `inspect(attrs)` connects with the service's connection parameters and returns an inventory. Credentials come from the profile in-process — never on a command line or in chat. Import the client SDK lazily (inside `inspect`) so loading the driver module stays cheap.

Inventory shape, one object per asset:

```json
{"locator": "...", "kind": "file|directory|table|topic|index",
 "format": "...", "schema": [{"name": "...", "type": "..."}],
 "partitioned_by": ["..."], "row_count": 0, "object_count": 0,
 "bytes": 0, "last_modified": "ISO-8601"}
```

The inventory can be large (thousands of assets) — `inspect_service.py` writes it to a file; never dump the full JSON to chat.

## Schema-fingerprint grouping (file-based storage)

Do not group objects by their directory path. Infer every object's schema, then group objects with an identical `(schema fingerprint, format)` into one logical asset. Detect a file's format from its **extension**, and parse it accordingly — never CSV-parse a `.parquet`/`.avro`/`.json` file (it yields a garbage wide schema). Path segments that vary within a group are partition keys: match `key=value` (Hive style), date patterns (`YYYY/MM/DD`, `dt=YYYY-MM-DD`, `year=/month=/day=`), and bare numeric ids. De-duplicate partition key names. Time partitioning is a scheduling hint — record the granularity.

`meshlib/schema.py` provides `group_by_fingerprint`, `csv_schema`, and `guess_type` — generic helpers any driver reuses.

## Delta / Iceberg tables

A Delta or Iceberg table on file storage is **one logical table**, not the `_delta_log/`, `metadata/`, and UUID-named data files it is physically made of. A file-store driver must detect the table root and emit a single `table` asset — never let the format internals become separate assets.

The table's own metadata is the schema authority and points at the underlying parquet/avro data:

- **Delta** — the schema is in a `_delta_log/*.json` commit (the `metaData` action's `schemaString`).
- **Iceberg** — the schema is in the latest `metadata/*.metadata.json` (the current schema's fields).

`meshlib/schema.py` provides `detect_table_roots`, `is_under_table_root`, `authoritative_metadata_key`, `delta_schema`, and `iceberg_schema`. When a table is also registered in a catalog service (Unity Catalog, Snowflake) and it is unclear which catalog owns it, the skill asks the user.
