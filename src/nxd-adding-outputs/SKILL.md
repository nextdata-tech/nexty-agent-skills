---
name: nxd-adding-outputs
description: Add or repair outputs in a Nextdata OS Python data product. Use when adding output semantic models, output ports, storage mappings, transform output parameters, file or table writes, RPC or MCP outputs, or output promises in spec.py, models.py, transform.py, contracts, or local validation scripts.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - MultiEdit
  - Glob
  - Grep
  - AskUserQuestion
metadata:
  author: nextdata
  version: 0.18.0
---

# NXD Adding Outputs

Add outputs to an existing Nextdata OS Python data product while keeping port names, transform signatures, storage config, and promises aligned.

## Setup

- Confirm `nxd-setup` has selected the mesh and produced `<session_config>`.
- Resolve `<app_url>` from the active mesh registry and use docs paths:
  - `<app_url>/docs/#/tutorials/guides/02-outputs`
  - `<app_url>/docs/#/tutorials/guides/03-promises`
  - `<app_url>/docs/#/tutorials/guides/01-semantic-model`
  - `<app_url>/docs/#/tutorials/guides/07-mcp`
- On Windows PowerShell, translate `<session_config>` and temp paths using `nxd-setup` conventions.

## Workflow

1. Inspect `spec.py`, `models.py`, `transform.py`, infra profile references, existing contracts, and existing output ports.
2. Confirm the output purpose, model schema, storage driver, service name, table/path/index name, and whether one port or multiple ports are needed.
3. Add or update the output semantic model in `models.py`. Reuse an existing model when the schema is identical.
4. Add the output port in `spec.py` using a service URL resolved from the active mesh app host, infra profile, and real service name.
5. Update `transform.py`. The transform parameter name must match the output port name after Python normalization: hyphens become underscores.
6. Write the output through the context type for the selected driver. Keep local-only helpers and credentials out of the deployment bundle via `.nxdignore`.
7. If quality enforcement is required, add a port-level promise. Promises attach to output ports, not to input declarations or standalone model definitions.
8. Update local validation to prove the generated output shape, not just input fetch.
9. Run validation:

```bash
nxd validate --config <session_config> <data_product_directory> --debug
```

## Driver Notes

- For Snowflake, Postgres, BigQuery, Databricks, and similar table stores, confirm database/schema/table behavior from the infra profile and docs before writing.
- For S3, ADLS, MinIO, and GCS, confirm format and partition path. Do not assume Parquet unless the user or existing product establishes it.
- For pgvector, confirm embedding dimension, text column, metadata shape, and whether the platform or library owns table creation. Prefer explicit vector config, for example `pg_vector_config(schema="public").vector("embedding", PgVectorType.VECTOR)`, unless the user or current SDK validation proves it must be omitted. Keep one model per pgvector port and align the model name with the intended physical table name.
- For scheduled pgvector writes, choose an idempotency strategy before launch: deterministic document IDs/upsert, truncate-then-write, or an explicitly approved append-only table. Do not catch every database exception and treat it as "table already exists"; check the specific error.
- For RPC/MCP outputs, inspect function request/response models and use the MCP docs path before editing.

### Scheduled pgvector full-refresh recipe

Use this pattern when the product rebuilds a rolling window on a schedule:

1. Resolve the target table from `pgvector.model_tables[output_model.name]`,
   falling back only when the context omits it.
2. Build the SQLAlchemy URL with URL-encoded username/password
   (`urllib.parse.quote_plus`) because service passwords may contain `@`, `/`,
   `:`, or spaces.
3. Before writing, check table existence with `to_regclass` or equivalent.
4. If the table exists, `TRUNCATE` it for full-refresh semantics.
5. If it does not exist, call `PGEngine.init_vectorstore_table(...)` with the
   known embedding dimension.
6. Use deterministic document IDs, for example `uuid.uuid5(namespace,
   stable_source_key)`, so reruns are inspectable and append/upsert variants can
   be added later.

Do not wrap `init_vectorstore_table` in a broad `except Exception` and assume
the table exists. That hides bad credentials, schema mistakes, and connection
failures.

## Guardrails

- Do not copy demo service URLs or output names from public examples.
- Do not remove existing output models unless the user explicitly asked for a breaking versioned change.
- If `nxd launch` reports removed semantic models, restore the prior model name or launch a versioned product instead of silently renaming.
