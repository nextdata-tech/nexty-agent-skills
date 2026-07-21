# Database connector: a live database connection

## Contents

- Scope
- The `sql_database` source shape
- Credential handling — read this before shipping
- Naming
- `transform/main.py` diff from the CSV template
- `requirements.txt` additions
- `spec.py` / `infra-profile.yaml` diffs
- Self-check (connectivity smoke test)

This is a sibling of the proven CSV connector documented inline in
`SKILL.md` — same closure shape (`duckdb` port, `PHYSICAL_MODELS`,
read-back assert, `.transform-complete`), no `data/` directory, no local
file export.

## Scope

Postgres and MySQL for this first cut — the two vendors dlt's
`sql_database` source has SQLAlchemy-dialect drivers proven against in this
pack. Other SQLAlchemy-dialect databases are architecturally plausible but
unverified here; do not claim support for a vendor that hasn't been proven.

## The `sql_database` source shape

```python
from dlt.sources.sql_database import sql_database

source = sql_database(
    credentials=<connection string or ConnectionStringCredentials>,
    schema=<db schema>,
    table_names=[<source table for each promised model>],
)
```

This returns one dlt resource per requested table, named after the *source*
table. Because the naming invariant requires the resource's final name to
equal the promised physical model name, **rename each resource** via
`.with_name(table_name)` using a model→source-table map — this is exactly
what the `db-source-tables` companion file below carries, so the source
table name and the model name never need to match.

## Credential handling — read this before shipping

For CSV, the committed "connector config" is just a non-secret path. For a
database connector it necessarily includes a real credential (host, user,
password). That value is delivered by writing it into the `db-source`
service's `attributes` in `infra-profile.yaml` — the desktop supervisor's
`generic-secrets` driver reads it from there and exposes it to the transform
as `secrets["db_source"]`.

- The companion file `db-source-tables` holds **only non-secret topology** —
  one line per model, `<model>=<schema-qualified source table name>`.
- The `db-source` service's `attributes` list carries the live payload as
  **one entry per connection field**, each shaped `{"key": <field>, "value":
  <live value>, "public": false}` — `host`, `port`, `database`, `schema`,
  `user`, `password` — never one attribute holding a nested object. Together
  they match exactly what `secrets["db_source"]` hands the transform as a
  dict. See the worked example below.
- **`value` is always a plain string** on the transform side — `port` arrives
  as `"5432"`, not `5432`; cast in `_build_connection_string` if the
  dialect's connection-string/DSN builder needs an int.
- **Set `public: false` on every attribute here.** The supervisor drops any
  attribute *not* marked `public: false` before it reaches template-render
  contexts — that's the actual credential boundary, not the closure
  directory. Don't rely on the default; it's inconsistent across call sites
  in the supervisor.
- **Never fabricate a credential the user hasn't supplied**, and never
  narrate a raw password in chat — enter it into `infra-profile.yaml` exactly
  as the user gave it, nowhere else.
- **The closure directory itself now holds a live credential in plaintext**
  — `public: false` only controls template-render exposure inside the
  supervisor, it does not make `infra-profile.yaml` safe to commit, zip, or
  hand off. Treat the whole closure directory as sensitive once this file
  carries a real password: don't commit it to a shared repo, don't attach it
  to a ticket or chat, and don't reuse it as a template for a different
  database without clearing the old credential first.
- This shape (`key`/`value`/`public`) is verified against the supervisor's
  `yaml_schemas::infra_profile::KeyValuePairWithPublic` type and
  `SecretsHandler` construction — not inferred from a single example.

## Naming

- Infra-profile service: `db-source`, driver `nxd:generic-secrets:1.0.0`.
- Transform secrets key: `secrets["db_source"]` — a dict with the connection
  fields the user supplied (host/port/database/schema/user/password), never
  a bare string.
- Companion file: `db-source-tables` — one line per model,
  `<model>=<source table>` (non-secret topology only; identity mapping if
  the source table already matches the model name).

These names are for exactly **one** database source. When this closure
needs two or more database sources (or mixes a database with another
connector type), label each instance instead — see
`reference/multi-source.md` for the full `db-source-<label>` /
`db_source_<label>` / `db-source-<label>-tables` pattern.

## `transform/main.py` diff from the CSV template

Same `duckdb` param/typing, `PHYSICAL_MODELS` discipline, read-back assert,
`write_disposition="replace"`, and `.transform-complete` touch as the CSV
template. Only the ingestion body changes:

```python
from dlt.sources.sql_database import sql_database

db_secrets = secrets["db_source"]  # dict: host/port/database/schema/user/password
connection_string = _build_connection_string(db_secrets)  # never hardcoded
table_map = _load_db_source_tables()  # parses the db-source-tables companion file

source = sql_database(
    credentials=connection_string,
    schema=db_secrets["schema"],
    table_names=list(table_map.values()),
)
readers = []
for model in PHYSICAL_MODELS:
    table_name = duckdb.model_tables[model]
    resource = source.resources[table_map[model]]
    readers.append(resource.with_name(table_name))
pipeline.run(readers, write_disposition="replace")
```

Build the connection string from `secrets["db_source"]` at runtime — never
hard-code host/user/password in the transform source. `_build_connection_string`
and `_load_db_source_tables` are **not** dlt or stdlib functions — the author
must write both: the former assembles a dialect-correct connection string
(Postgres and MySQL differ) from the `db_source` dict fields, the latter
parses the `db-source-tables` companion file's `<model>=<table>` lines into a
dict. Neither is optional boilerplate; a transform that calls them without
defining them raises `NameError` at runtime.

## `requirements.txt` additions

Base pins unchanged. Add `dlt[sql_database]==1.28.2` plus **exactly one**
vendor driver matched to what the user actually has — `psycopg2-binary` for
Postgres, `pymysql` for MySQL. Never install both speculatively.

## `spec.py` / `infra-profile.yaml` diffs

- `spec.py`: `_db = "/infra-profile/desktop-local#/services/db-source"`,
  `.secrets([_db])`. Everything else (`.promise`, `.model`,
  `.port("duckdb", ...)`, no `.semantic_tools()`) is identical to the CSV
  template.
- `infra-profile.yaml`: third service named `db-source` (same driver
  `nxd:generic-secrets:1.0.0`), with its `attributes` populated with the
  live connection credentials:

  ```yaml
    - name: db-source
      driver: nxd:generic-secrets:1.0.0
      attributes:
        - key: host
          value: <live host>
          public: false
        - key: port
          value: <live port>
          public: false
        - key: database
          value: <live database>
          public: false
        - key: schema
          value: <live schema>
          public: false
        - key: user
          value: <live user>
          public: false
        - key: password
          value: <the live password the user supplied>
          public: false
  ```

  **No `data/` directory, no path file** — `db-source-tables` is the only
  companion artifact, and it stays non-secret topology only. For 2+ database
  sources, add one labeled service per instance instead (`db-source-<label>`
  / `secrets["db_source_<label>"]`) — see `reference/multi-source.md`.

## Self-check (connectivity smoke test)

A database connector needs live credentials to dry-run at all — unlike CSV
or another local file connector, there's no offline structural check that
proves the data actually loads. When credentials are available in the
authoring session, do **not** reuse the full `pipeline.run(...)` ingestion
path unmodified — pulling entire production tables just to prove
connectivity is wasteful and, for large or sensitive tables, unnecessary
risk. Instead call `.add_limit(1)` on each resource before running the
pipeline (`source.resources[table_map[model]].add_limit(1)`) so the
connectivity check pulls at most one row per model, then assert
`row_count > 0` per model — **not** an exact fixture count, since live data
isn't static. When credentials are not available in-session, report the
connectivity self-check as **not run** — do not claim it passed. Structural
checks (naming invariant, no `.semantic_tools()`, import correctness) still
run regardless.
