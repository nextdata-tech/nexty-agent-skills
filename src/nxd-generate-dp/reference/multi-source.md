# Multiple sources of the same (or mixed) connector types

## Contents

- The label rule
- Naming table
- Worked example: two CSV sources
- What does NOT change

Every connector type documented elsewhere in this pack (`csv-source` inline
in `SKILL.md`, `file-source.md`) assumes exactly one instance per closure.
This doc is the sibling case: a closure that needs **two or more** sources —
two CSV exports, a CSV plus a JSON export, a materialized database source
alongside a materialized API source (see `reference/database-source.md` /
`reference/api-source.md` — both collapse to CSV before this point), whatever
the mix — without any of them colliding on the same fixed name.

## The label rule

**A connector type with exactly one instance in the closure keeps today's
plain, unlabeled name — completely unchanged.** This is not optional: the
CSV single-source path in particular is regression-tested by literal string
assertions, so never label a source that is the only instance of its type.

**Once a type has two or more instances**, each instance gets an
author-chosen **source label**: short, lowercase, hyphen-separated (e.g.
`orders`, `users`, `crm`), unique among instances of *that* type. Reusing a
label across different types is harmless (`csv-source-orders` and
`file-source-orders` don't collide as service names) but avoid it for
clarity.

Database and API sources are materialized to CSV before this step (see
`reference/database-source.md` / `reference/api-source.md`), so two database
sources, or a database plus an API, both just become two labeled CSV
sources — the `csv-source` row below, nothing special.

## Naming table

| Case | Service | `secrets[...]` key | Companion artifact | `spec.py` var |
|---|---|---|---|---|
| One CSV (unchanged) | `csv-source` | `csv_source` | `csv-source-path` | `_csv` |
| 2+ CSVs, labeled | `csv-source-<label>` | `csv_source_<label>` | `csv-source-<label>-path` | `_csv_<label>` |
| One file source (unchanged) | `file-source` | `file_source` | `file-source-path` | `_file` |
| 2+ file sources, labeled | `file-source-<label>` | `file_source_<label>` | `file-source-<label>-path` | `_file_<label>` |

The driver id (`nxd:generic-secrets:1.0.0`) and `attributes: []` never
change — only the name.

## Worked example: two CSV sources

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
    - name: csv-source-orders
      driver: nxd:generic-secrets:1.0.0
      attributes: []
    - name: csv-source-support
      driver: nxd:generic-secrets:1.0.0
      attributes: []
```

`spec.py` binds one variable per instance and passes both through
`.secrets([...])`:

```python
_csv_orders = "/infra-profile/desktop-local#/services/csv-source-orders"
_csv_support = "/infra-profile/desktop-local#/services/csv-source-support"
_compute = "/infra-profile/desktop-local#/services/python-compute"
_duckdb = "/infra-profile/desktop-local#/services/duckdb"

spec = (
    data_product(name="<dp-name>", domain="desktop.local", version="0.0.1",
                 infra_profile="desktop-local")
    .transform(
        script("transform/main.py")
        .compute(_compute)
        .secrets([_csv_orders, _csv_support])
    )
    .output(_output)
)
```

`transform/main.py` receives both secrets entries and reads one root
directory per label; each promised model belongs to exactly one label,
resolved by which labeled root (`data-orders/`, `data-support/`) it lives
under:

```python
readers = []
for label, secrets_key, models in (
    ("orders", "csv_source_orders", ("orders", "order_items")),
    ("support", "csv_source_support", ("tickets",)),
):
    source_root = Path(secrets[secrets_key])
    for model in models:
        table_name = duckdb.model_tables[model]
        reader = filesystem(bucket_url=str(source_root / model), file_glob="*.csv") | read_csv()
        readers.append(reader.with_name(table_name))
pipeline.run(readers, write_disposition="replace")
```

The read-back assert, `write_disposition="replace"`, and
`.transform-complete` touch are unchanged — they operate on the full
`PHYSICAL_MODELS` set regardless of how many source instances contributed to
it.

## What does NOT change

- The physical-model naming invariant (`models.py` == `.promise` ==
  `PHYSICAL_MODELS` == `main.<name>`) — every model still belongs to exactly
  one source instance, it just resolves through that instance's labeled
  root directory instead of the shared `data/`.
- The `duckdb` output port name, `write_disposition="replace"`, and
  `.transform-complete` touch.
- The single-instance default names for any type that only has one source —
  never label a type's sole instance.
