# Multiple sources of the same (or mixed) connector types

## Contents

- The label rule
- Naming table
- Worked example: two database sources
- Applying the pattern to file / API / CSV sources
- What does NOT change

Every connector type documented elsewhere in this pack (`csv-source` inline
in `SKILL.md`, `file-source.md`, `database-source.md`, `api-source.md`)
assumes exactly one instance per closure. This doc is the sibling case: a
closure that needs **two or more** sources — two databases, a database plus
a REST API, two CSV exports, whatever the mix — without any of them
colliding on the same fixed name.

## The label rule

**A connector type with exactly one instance in the closure keeps today's
plain, unlabeled name — completely unchanged.** This is not optional: the
CSV single-source path in particular is regression-tested by literal string
assertions, so never label a source that is the only instance of its type.

**Once a type has two or more instances**, each instance gets an
author-chosen **source label**: short, lowercase, hyphen-separated (e.g.
`orders`, `users`, `crm`), unique among instances of *that* type. Reusing a
label across different types is harmless (`db-source-orders` and
`api-source-orders` don't collide as service names) but avoid it for
clarity.

## Naming table

The "(unchanged)" rows restate SKILL.md's canonical connector-types table
deliberately — each sits next to its labeled counterpart so the rename
pattern (`<name>` → `<name>-<label>`) reads in one glance. SKILL.md's table
stays the source of truth for the unlabeled names themselves; a rename there
must be mirrored here.

| Case | Service | `secrets[...]` key | Companion artifact | `spec.py` var |
|---|---|---|---|---|
| One database (unchanged) | `db-source` | `db_source` | `db-source-tables` | `_db` |
| 2+ databases, labeled | `db-source-<label>` | `db_source_<label>` | `db-source-<label>-tables` | `_db_<label>` |
| One file source (unchanged) | `file-source` | `file_source` | `file-source-path` | `_file` |
| 2+ file sources, labeled | `file-source-<label>` | `file_source_<label>` | `file-source-<label>-path` | `_file_<label>` |
| One API (unchanged) | `api-source` | `api_source` | `api-source-endpoints` | `_api` |
| 2+ APIs, labeled | `api-source-<label>` | `api_source_<label>` | `api-source-<label>-endpoints` | `_api_<label>` |
| One CSV (unchanged) | `csv-source` | `csv_source` | `csv-source-path` | `_csv` |
| 2+ CSVs, labeled | `csv-source-<label>` | `csv_source_<label>` | `csv-source-<label>-path` | `_csv_<label>` |

The driver id (`nxd:generic-secrets:1.0.0`) never changes — only the name.
`attributes` follows the single-instance rule per type: `[]` for
`csv-source-<label>` / `file-source-<label>` (nothing secret to carry — see
`reference/file-source.md`); for `db-source-<label>` / `api-source-<label>`,
one flat `{"key": <property>, "value": <live value>, "public": <bool>}`
attribute per connection field — the label lives on the *service* name
(`db-source-orders`), not on the attribute keys, which stay the plain
property names (`host`, `port`, ...) within each labeled service — see
`reference/database-source.md` / `reference/api-source.md` for the exact
per-property list and the `public:` value per property (secrets `false`,
non-secret topology `true`).

## Worked example: two database sources

`infra-profile.yaml` grows past three services — one connector service per
source instance, alongside the fixed `duckdb` and `python-compute`:

```yaml
apiVersion: infra.nextdata.com/v1
kind: Profile
metadata:
  name: desktop-local
spec:
  services:
    - name: duckdb
      driver: nxd:local/duckdb/storage:0.1.0
      attributes: []
    - name: python-compute
      driver: nxd:local/python/compute:0.1.0
      attributes: []
    - name: db-source-orders
      driver: nxd:generic-secrets:1.0.0
      attributes:
        - key: host
          value: <live host>
          public: true
        - key: port
          value: <live port>
          public: true
        - key: database
          value: <live database>
          public: true
        - key: schema
          value: <live schema>
          public: true
        - key: user
          value: <live user>
          public: false
        - key: password
          value: <the live password the user supplied>
          public: false
    - name: db-source-users
      driver: nxd:generic-secrets:1.0.0
      # Same six attributes as db-source-orders above (host/port/database/
      # schema `public: true`, user/password `public: false`) — its own values,
      # not shared with db-source-orders. See reference/database-source.md
      # for the canonical per-field list.
      attributes: [...]
```

`spec.py` binds one variable per instance and passes both through
`.secrets([...])`:

```python
_db_orders = "/infra-profile/desktop-local#/services/db-source-orders"
_db_users = "/infra-profile/desktop-local#/services/db-source-users"
_compute = "/infra-profile/desktop-local#/services/python-compute"
_duckdb = "/infra-profile/desktop-local#/services/duckdb"

spec = (
    data_product(name="<dp-name>", domain="desktop.local", version="0.0.1",
                 infra_profile="desktop-local")
    .transform(
        script("transform/main.py")
        .compute(_compute)
        .secrets([_db_orders, _db_users])
    )
    .output(_output)
)
```

`transform/main.py` receives both secrets entries and builds one connection
per label; each promised model resolves to exactly one label via its
labeled companion file (`db-source-orders-tables`, `db-source-users-tables`
— each a `<model>=<source table>` map covering only the models that instance
owns):

```python
readers = []
for label, secrets_key, tables_file in (
    ("orders", "db_source_orders", "db-source-orders-tables"),
    ("users", "db_source_users", "db-source-users-tables"),
):
    db_secrets = secrets[secrets_key]
    connection_string = _build_connection_string(db_secrets)
    table_map = _load_source_tables(tables_file)
    source = sql_database(credentials=connection_string,
                           schema=db_secrets["schema"],
                           table_names=list(table_map.values()))
    for model in table_map:
        table_name = duckdb.model_tables[model]
        readers.append(source.resources[table_map[model]].with_name(table_name))
pipeline.run(readers, write_disposition="replace")
```

The read-back assert, `write_disposition="replace"`, and
`.transform-complete` touch are unchanged — they operate on the full
`PHYSICAL_MODELS` set regardless of how many source instances contributed to
it.

## Applying the pattern to file / API / CSV sources

Same shape: swap `db-source-<label>`/`db_source_<label>`/`sql_database` for
`file-source-<label>`/`file_source_<label>`/the `dlt.sources.filesystem`
reader, `api-source-<label>`/`api_source_<label>`/`rest_api_resources`, or
`csv-source-<label>`/`csv_source_<label>`/`read_csv` — each labeled file or
CSV source also gets its own root directory (`data-<label>/<model>/*.csv`
instead of the shared `data/`) so two file-based sources' exports never
overlap on disk.

## What does NOT change

- The physical-model naming invariant (`models.py` == `.promise` ==
  `PHYSICAL_MODELS` == `main.<name>`) — every model still belongs to exactly
  one source instance, it just resolves through that instance's labeled
  companion file instead of an unlabeled one.
- The `duckdb` output port name, `write_disposition="replace"`, and
  `.transform-complete` touch.
- The single-instance default names for any type that only has one source —
  never label a type's sole instance.
