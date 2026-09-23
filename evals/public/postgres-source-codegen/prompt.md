# Scenario: Generate a Postgres data-product source

The workspace contains `source-contract.yaml`, a pinned synthetic contract for
a read-only Postgres source with two tables. It is a local contract only: do
not connect to a database, install dependencies, or invent credentials.

## Task

Read `source-contract.yaml` before authoring. Create a Python-only local
desktop data-product closure at the workspace root with:

- `spec.py`
- `models.py`
- `infra-profile.yaml`
- `transform/main.py`
- `db-source-tables`
- `requirements.txt`
- `README.md`
- `.gitignore`
- `SENSITIVE`

Use the documented `db-source` recipe and dlt's `sql_database` source. Build
the connection string from the flat `secrets` fields, pass the configured
schema and both source table names, and rename each returned resource to the
promised physical model name. Keep `db-source-tables` to non-secret model to
table mappings only. The supplied password is synthetic eval input: place it
only in the profile with `public: false`, never in source code or your answer.

This is a read-only source. Do not export tables into `data/`, add write SQL,
run a live connectivity check, or claim a database build. A static syntax
check is sufficient.

## Eval boundary

The evaluator checks the generated closure statically. It does not provide a
Postgres server and it does not run dlt.
