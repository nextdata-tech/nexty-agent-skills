# Multiple sources of the same (or mixed) connector types

## Contents

- The label rule
- Colliding keys: prefix in the attribute keys
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
author-chosen **source label**: short, lowercase, hyphen-separated and
carrying **no underscore** (e.g. `orders`, `users`, `crm`, `orders-eu`),
unique across **every labeled instance in the closure — not merely within its
own type**. Both halves of that rule are driven by the `generic-secrets`
connectors — `db-source` and `api-source` — because those are the instances the
transform separates by `<label>_` key prefix over a single flat `secrets` map
spanning every service.

- **No underscore in a label** is what keeps `<label>_` unambiguous. Because
  labels use hyphens, `orders_` cannot match an `orders-eu_*` key and the two
  instances partition cleanly. Sneak an underscore in and that stops holding:
  `orders` alongside `orders_eu` is illegal, because `orders_` then matches
  every `orders_eu_*` key and silently folds the two together.
- **Unique across types, not per type**, because the prefix is the label
  alone — the type is not part of it. `db-source-orders` and
  `api-source-orders` both prefix their keys `orders_`, so one recovery loop
  drags both services' fields into a single instance's dict, and any attribute
  the two happen to share (`region`, `user`, `token`) collides outright in the
  merge. Distinct *service* names do not rescue this: the service name is
  discarded before the transform sees anything (see Colliding keys below).

**`csv-source` / `file-source` instances separate by a different mechanism**, so
neither constraint is load-bearing for them: their key is contributed by their
own driver in the *suffix* form `csv_source_<label>` / `file_source_<label>` (as
the naming table below shows), which means there is no `attributes` entry to
prefix and no prefix scan to confuse. Both rules still apply to them, but only
as harmless over-strictness — `csv_source_orders` never matches an `orders_`
scan either way, and one label namespace across the whole closure is easier to
keep right than a per-type one.

**desktop source-aligned inputs are the exception:** this is a
transform-service naming rule for labeled CSVs, not permission to bind
`.input(...).source(_csv_<label>)`; those inputs use the one unlabeled `_csv`.

## Colliding keys: prefix in the attribute keys

**`secrets` is one flat map, so any two services that declare the same attribute
`key` collide.** The supervisor merges every service named in `.secrets([...])`
into a single dict keyed by the raw attribute `key` — there is no per-service
level to separate them. For a `generic-secrets` service (`db-source`,
`api-source`) those keys are exactly the `attributes` you wrote, and the service
name does not appear among them. (A `csv-source` / `file-source` does not carry
`attributes`; its key — `csv_source`, `file_source` — is contributed by its own
driver and is unaffected by this section.) Two
`db-source-<label>` services that both declare `host` resolve to one
`secrets["host"]`, and which one wins is the merge order, not your intent.

**This fails silently.** The losing value is not reported, not logged, and not
visible to the transform — there is no key to compare against, because the
duplicate simply never existed in the merged map. A closure that reads the
survivor connects to the wrong database and ingests real rows from it. Renaming
the *services* does not help: the service name is discarded before the transform
sees anything.

**Check for it while writing the profile.** List the attribute keys of every
service named in `.secrets([...])`, and treat any key appearing twice as a
collision. It is an authoring-time check because it is not a runtime one.

**Fix it by prefixing the attribute `key` in the profile**, since the key is the
only thing that survives the merge:

- **Two or more `generic-secrets` instances of the same type** (`db-source`,
  `api-source`) — prefix *every* key of each instance with its label:
  `orders_host`, `orders_password`, `users_host`, `users_base_url`. Uniform
  prefixing keeps the transform's recovery loop regular
  (`k.startswith(f"{label}_")`, as in the worked example below) and survives
  someone later adding a field to one instance. There is nothing to do here for
  labeled `csv-source` / `file-source` instances: their driver already emits a
  distinct `csv_source_<label>` / `file_source_<label>` key per instance.
- **Mixed types that happen to share a key** — a `db-source` and an `api-source`
  that both carry `region`, `user`, or a `token`. The canonical field sets do not
  overlap, so this arises from fields *you* add. Prefix at least the colliding
  keys; prefixing that whole instance is simpler to keep right than a
  per-key exception list.

The service name still carries the label — it names the instance in the profile
and in `.secrets([...])` — but only the attribute keys reach the transform.

## Naming table

The "(unchanged)" rows restate SKILL.md's canonical connector-types table
deliberately — each sits next to its labeled counterpart so the rename
pattern (`<name>` → `<name>-<label>`) reads in one glance. SKILL.md's table
stays the source of truth for the unlabeled names themselves; a rename there
must be mirrored here.

| Case | Service | `secrets[...]` key | Companion artifact | `spec.py` var |
|---|---|---|---|---|
| One database (unchanged) | `db-source` | the field keys — `host`, `port`, … | `db-source-tables` | `_db` |
| 2+ databases, labeled | `db-source-<label>` | `<label>_<field>` — `orders_host`, … | `db-source-<label>-tables` | `_db_<label>` |
| One file source (unchanged) | `file-source` | `file_source` | `file-source-path` | `_file` |
| 2+ file sources, labeled | `file-source-<label>` | `file_source_<label>` | `file-source-<label>-path` | `_file_<label>` |
| One API (unchanged) | `api-source` | the attribute keys — `base_url`, … | `api-source-endpoints` | `_api` |
| 2+ APIs, labeled | `api-source-<label>` | `<label>_<attr>` — `orders_base_url`, … | `api-source-<label>-endpoints` | `_api_<label>` |
| One CSV (unchanged) | `csv-source` | `csv_source` | `csv-source-path` | `_csv` |
| 2+ CSVs, labeled, transform-only | `csv-source-<label>` | `csv_source_<label>` | `csv-source-<label>-path` | `_csv_<label>` |

For CSV instances the driver is `nxd:local/file/storage:0.1.0`; only the
service name changes. **Runtime boundary:** labeled CSV services may appear in
`.transform(...).secrets([...])`, but not in desktop
`.input(...).source(...)`. Every source-aligned desktop input, even a
non-custom one, uses the exact unlabeled `_csv` binding and the one
`csv-source-path`; multiple input declarations may share it. Other connector
types retain their documented drivers.
`attributes` follows the single-instance rule per type: `[]` for
`csv-source-<label>` / `file-source-<label>` (nothing secret to carry — see
`reference/file-source.md`); for `db-source-<label>` / `api-source-<label>`,
one flat `{"key": <property>, "value": <live value>, "public": <bool>}`
attribute per connection field, **each key prefixed with the label**
(`orders_host`, `orders_port`, ...). The service name carries the label too,
but it is discarded before the transform sees anything, so the key is what
separates the instances — see Colliding keys above, and see
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
      # Every key carries the `orders_` label prefix. Unprefixed, these six
      # would collide with db-source-users below in the flat merge and one
      # instance would silently win.
      attributes:
        - key: orders_host
          value: <live host>
          public: true
        - key: orders_port
          value: <live port>
          public: true
        - key: orders_database
          value: <live database>
          public: true
        - key: orders_schema
          value: <live schema>
          public: true
        - key: orders_user
          value: <live user>
          public: false
        - key: orders_password
          value: <the live password the user supplied>
          public: false
    - name: db-source-users
      driver: nxd:generic-secrets:1.0.0
      # Same six attributes, prefixed `users_` instead (users_host, users_port,
      # users_database, users_schema `public: true`; users_user, users_password
      # `public: false`) — its own values, not shared with db-source-orders.
      # See reference/database-source.md for the canonical per-field list.
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
for label, tables_file in (
    ("orders", "db-source-orders-tables"),
    ("users", "db-source-users-tables"),
):
    # `secrets` is ONE flat map across every service, so each instance's fields
    # are recovered by their `<label>_` prefix — there is no per-service level.
    # This is only a partition because labels carry no underscore and are unique
    # closure-wide (see the label rule): an `orders_eu` label would make
    # `orders_` match every `orders_eu_*` key, and an `api-source-orders` reusing
    # the `orders` label would fold its fields into this dict too.
    db_secrets = {k[len(label) + 1:]: v for k, v in secrets.items()
                  if k.startswith(f"{label}_")}
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

Same shape: swap `db-source-<label>`/`<label>_<field>`/`sql_database` for
`file-source-<label>`/`file_source_<label>`/the `dlt.sources.filesystem`
reader, `api-source-<label>`/`<label>_<attr>`/`rest_api_resources`, or
`csv-source-<label>`/`csv_source_<label>`/`read_csv` **inside the transform**.
Labeled CSV roots (`data-<label>/<model>/*.csv`) are transform-only; they do
not create a labeled desktop source-aligned input. Multiple source-aligned
inputs instead share `_csv` and `csv-source-path`.

## What does NOT change

- The physical-model naming invariant (`models.py` == `.promise` ==
  `PHYSICAL_MODELS` == `main.<name>`) — every model still belongs to exactly
  one source instance, it just resolves through that instance's labeled
  companion file instead of an unlabeled one.
- The `duckdb` output port name, `write_disposition="replace"`, and
  `.transform-complete` touch.
- The single-instance default names for any type that only has one source —
  never label a type's sole instance.
