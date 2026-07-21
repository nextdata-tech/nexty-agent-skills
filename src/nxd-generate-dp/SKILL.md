---
name: nxd-generate-dp
description: Generates the COMPLETE runnable Python-only data-product closure for lean-desktop Nextdata OS (the desktop supervisor) from a natural-language intent, an inferred semantic model, and a connector config — spec.py + models.py + infra-profile.yaml + transform/main.py + requirements + the connector artifact (a local file export, a live database connection, or an off-mesh REST API), ready to boot locally and produce a queryable DuckDB result. The supervisor compiles spec.py into the kernel definition YAML at create time, so the author never hand-writes deployment-spec / manifest / models YAML. Use when the task is to "generate a data product", "build a DP from intent", "assemble a runnable data product around an inferred semantic model", or to turn a connector config plus stakeholder questions into a local desktop DP. Pairs with nxd-semantic-data-product, which INFERS the semantic model this skill PLACES and assembles the closure around. Not for the k8s/Snowflake topology — use nxd-data-product-builder there.
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
  version: 0.12.0
---

# nxd-generate-dp skill

## Overview

This skill assembles the **complete Python-only definition closure** for a
local (desktop) data product from these inputs:

1. **Intent** — the user's natural-language description of what the DP is for.
2. **Inferred semantic model** — the per-column semantic roles produced by the
   **nxd-semantic-data-product** skill's inference mode (its `schema.json`
   profile + role declarations). That skill designs the roles; this skill
   places them. Do not redesign them.
3. **Connector config(s)** — one or more, each naming where the source data
   lives and its **connector type**. Never invent connection details or
   credentials for a database or API connector.

**Connector types at a glance** — the canonical mapping; every other mention below points back here instead of restating it:

| Type | Service | `secrets[...]` key | Companion artifact |
|---|---|---|---|
| CSV (proven, fully-inlined default below) | `csv-source` | `csv_source` | `csv-source-path` + `data/` |
| Other file (JSON/JSONL/Parquet) — `reference/file-source.md` | `file-source` | `file_source` | `file-source-path` + `data/` |
| Database — `reference/database-source.md` | `db-source` | `db_source` | `db-source-tables`, no `data/` |
| REST API — `reference/api-source.md` | `api-source` | `api_source` | `api-source-endpoints`, no `data/` |

Names above are for exactly one instance of a type — for 2+, label each per `reference/multi-source.md`.

The output is a directory the **desktop supervisor** can compile, pin, boot,
and publish: the supervisor **compiles `spec.py` into the kernel definition
YAML at create time**, snapshots the closure, boots the local kernel, runs the
transform (dlt through the DuckDB output port), verifies staging, promotes the
artifact, and stands up the semantic MCP endpoint over it.

## The closure layout

The author emits **Python and prerequisite config only** — the deployment
YAMLs are BUILD PRODUCTS the supervisor compiles from `spec.py` at pin time:

```
<dp-root>/
├── spec.py                # author-facing definition: promises + transform + output port
├── models.py              # semantic models + placed semantic roles
├── infra-profile.yaml     # the desktop-local profile: duckdb + python-compute + csv-source
├── transform/
│   └── main.py            # the dlt-through-port ingest (standalone entrypoint)
├── requirements.txt       # proven pins (below)
├── csv-source-path        # one line: relative path to the CSV export root
└── data/                  # the connector export: data/<model>/*.csv
    └── <model>/…
```

> This is the CSV layout, the proven default; other types swap in a
> different companion artifact per the table above.

**The author NEVER writes `deployment-spec.yaml`, `manifest.yaml`, or
`models.yaml`.** Those three are now compiled by the desktop supervisor from
`spec.py` + `models.py` when it creates and pins the DP. Emitting them by hand
is wrong — the supervisor owns their shape and will overwrite them. Your
source of truth is the Python: get `spec.py` and `models.py` right and the
compiled YAML follows.

> Layout note: unlike the k8s `.semantic_tools()` topology (modules flat at
> the DP root, no subdir), the desktop closure keeps the transform at
> `transform/main.py` — the directory the snapshot pins and the local Python
> compute driver executes. `models.py`/`spec.py` sit at the root, imported by the compiler.

---

## THE NAMING INVARIANT (the correctness spine — protect it everywhere)

One lowercase, unquoted, snake_case name per model, agreed on by **three
authored surfaces** (the supervisor derives the compiled-YAML `models.yaml`
name and the `model_tables` identity map from these — you do not author them):

| Surface | Where the name appears |
|---|---|
| `models.py` | `semantic_model("<name>")` |
| `spec.py` | `.promise(<name>)` — imported from `models` |
| the connector's per-model reference | `data/<name>/` for a file connector (CSV/JSON/JSONL/Parquet); a `db-source-tables` entry for a database connector; an `api-source-endpoints` entry for a REST API connector |
| the physical table | what dlt writes: `main.<name>` |

`.model(name)` == `main.<name>` == the dlt-written table, **unquoted
lowercase**. dlt normalizes names, so assert its output against the promised
physical models—not the whole `model_tables` map, which also includes semantic
views. Attribute names are byte-exact CSV headers (post-dlt snake_case).

Separately, the **storage output port MUST be named `duckdb`**, matched by
the transform param (Step 4) — the local DuckDB driver requires it; `output` is wrong.

---

## Workflow

### Step 1 — Collect the inputs

- The intent tells you the DP `name`, description, and which questions the
  semantic layer must answer.
- The inferred model gives each base model's primary key, dimensions, joins,
  PII flags, metrics, and column types. Base roles and metric views are
  different authored objects — see Step 3.
- Each connector config names a **connector type** (CSV / other local file /
  database / REST API) plus its type-specific location. For CSV: confirm one
  subdirectory per model (`<root>/<model>/*.csv`) and read its headers; stop
  and surface a model/directory mismatch rather than inventing or dropping
  models. For the other three types, follow `reference/file-source.md` /
  `database-source.md` / `api-source.md` — for database/API, confirm the
  user supplied real connection details; never invent them.

### Step 2 — `infra-profile.yaml`: the desktop-local profile (emitted prerequisite)

The desktop closure ships its own infra profile declaring the three local
services the spec references. Emit it **verbatim in this shape** (only rarely
does anything here vary — the driver ids and service names are fixed):

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
    - name: csv-source
      driver: nxd:generic-secrets:1.0.0
      attributes: []
```

- `metadata.name` is `desktop-local` — it MUST match `infra_profile=` in
  `spec.py` and the `/infra-profile/desktop-local#/...` service refs.
- Three services: `duckdb` (storage), `python-compute` (runs the transform),
  `csv-source` (generic-secrets, delivers the CSV export root). None carry a
  live value here — `duckdb`/`python-compute` never do, and `csv-source`'s
  export root is non-secret topology (covered by `csv-source-path` below) —
  so all three stay `attributes: []`.
- The closure also carries **`csv-source-path`** — one line, the
  **relative** path from the closure root to the CSV export root (e.g.
  `data`); the supervisor resolves it inside the pinned snapshot, so an
  absolute path escapes the snapshot and fails.
- **Other connector types**: only the third service's *name* changes, per
  the table above. A connector needing a **real credential** (database, REST
  API) populates that service's `attributes` instead — see
  `reference/database-source.md` / `reference/api-source.md` for the shape;
  `csv-source`/`file-source` have no credential to carry. For 2+ sources of
  one type, add one service per instance — see `reference/multi-source.md`.

> The supervisor compiles `deployment-spec.yaml`, `manifest.yaml`, and
> `models.yaml` from `spec.py` + `models.py` at pin time — including the
> `model_tables` identity map, the staging-path placeholder, and the compiled
> semantic roles the semantic child reads. **You never write those three files.**

### Gate — validate base-model primary keys before authoring

Every promised physical model needs one or more `primary_key()` fields. Before
authoring `models.py`, validate existing CSV columns whose non-null value tuple
is unique **across the complete supplied export** (all CSV files together).
Prefer one source column; use a composite only when it is the defensible entity
key. Never use row numbers, measures, or altered source data. If the evidence
is absent, stop and ask for the source entity/event key; a unique sample is not
proof for a future export. This replace-only flow excludes append/upsert
semantics, which require a separately designed stable source key.

### Step 3 — `models.py`: place the inferred roles with the public DSL

Author `models.py` with the **real public semantic DSL**. Import the role
builders and wrap each field:

```python
from nxd.spec import semantic_model, field, primary_key, dimension, join
from nxd.spec.data_types import number, string
```

Here you place the base table roles, then add one semantic view for each set of
metrics over that table:

- `semantic_model("<name>")` — the bare lowercase physical table name.
- `.schema({...})` mapping each CSV header column (byte-exact) to a typed
  value. A column that carries a semantic role is authored as
  `field(<type>(), <role>())`; a column with no role is authored as the bare
  type (`"country": string()`), so it still reaches the compiled schema.
- One or more compatible roles per role-bearing base field. **Base models carry ONLY
  `primary_key()`, `dimension(...)`, or `join(...)`.** Metrics are consume-time
  / view-level — the DSL RAISES if you attach a metric to a base-model field.
- A metric belongs on `semantic_view("<base>_metrics", <base>)` with
  `metric_field(<type>(), metric(Agg.<AGG>, of=<base>.field("<column>"), ...))`.
  The view is a query-time model, not a physical table.

Role builders (verified DSL facts):

| Role | Form |
|---|---|
| primary key | `field(number(), primary_key())` — the entity key. Emit `primary_key()`; NEVER the deprecated `grain` alias. |
| dimension | `field(string(), dimension(name="<concept>", pii=<inferred flag>))` |
| join (N:1) | `field(number(), join(to="<model>", to_column="<col>"))` — note `to=` and `to_column=`, NOT `to_model=` |

Columns the inferred model left unannotated stay bare-typed (do not invent
roles no question motivated). No marker model: desktop produce-verification is
the transform's `.transform-complete` file, not a marker row.

Worked example (matches the proven closure): see `reference/models-example.md`.

Data-type mapping (inferred type → `nxd.spec.data_types`):

| Inferred | `models.py` |
|---|---|
| string | `string()` |
| int / number | `number()` |
| number / double / float | `number()` |
| bool | `boolean()` |
| date | `date32()` |

### Step 4 — `transform/main.py`: the dlt-through-port ingest

The transform receives the typed **output port handle** (`DuckDbOutput`: `path`,
`schema`, `model_tables`) and connector secrets, streams each **promised
physical model** CSV directory through dlt, then asserts the produced table
names. The handle param is **`duckdb`**, matching the port in Step 5. Declare
`PHYSICAL_MODELS` from the `.promise(...)` calls; use `duckdb.model_tables` only
to resolve those table names. It can also contain `.model(...)` semantic views,
which have neither a CSV directory nor a physical DuckDB table.

```python
"""<dp-name>: load the CSV connector export into the local DuckDB output port."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# S0 source-checkout shim. The supervisor exports this for an interpreter
# without the wheel; the guarded lookup keeps normal wheel-based runs working.
_repo_root = os.environ.get("NXD_DESKTOP_REPO_ROOT")
if _repo_root:
    for _source in reversed((
        Path(_repo_root) / "components/nxd_py/data_product",
        Path(_repo_root) / "components/nxd_py/core",
        Path(_repo_root) / "components/nxd_py/drivers",
    )):
        sys.path.insert(0, str(_source))

import dlt
from dlt.sources.filesystem import filesystem, read_csv

from nxd import data_product
from nxd.core.context import DuckDbOutput

# Base semantic_model names promised by spec.py; never semantic views.
PHYSICAL_MODELS = ("<base_model>",)


@data_product.on_transform()
def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any]) -> None:
    """Stream each model's CSV directory into the DuckDB output port."""
    source_root = Path(secrets["csv_source"])
    # Keep ALL dlt state run-local (next to the staging file) — never ~/.dlt.
    run_dir = Path(duckdb.path).parent
    pipelines_dir = run_dir / "dlt-pipelines"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DLT_DATA_DIR"] = str(run_dir / "dlt-data")

    pipeline = dlt.pipeline(
        pipelines_dir=str(pipelines_dir),
        destination=dlt.destinations.duckdb(credentials=duckdb.path),
        dataset_name=duckdb.schema,
    )
    readers = []
    for model in PHYSICAL_MODELS:
        table_name = duckdb.model_tables[model]
        reader = filesystem(
            bucket_url=str(source_root / model), file_glob="*.csv"
        ) | read_csv()
        readers.append(reader.with_name(table_name))
    pipeline.run(readers, write_disposition="replace")

    # dlt must write exactly the promised physical tables, never semantic views.
    actual = set(pipeline.default_schema.data_table_names())
    expected = {duckdb.model_tables[model] for model in PHYSICAL_MODELS}
    if actual != expected:
        raise RuntimeError(
            f"dlt produced tables {sorted(actual)!r}, expected {sorted(expected)!r}"
        )
    # Produce-verification marker: the supervisor's readiness gate waits for it.
    (run_dir / ".transform-complete").touch()


if __name__ == "__main__":
    data_product.main()
```

Contract facts baked into that template — keep every one:

- The transform param is named **`duckdb`** — it MUST match the storage output
  port name (`duckdb`), and it MUST be typed `DuckDbOutput` (an untyped param
  gets a raw context with no `path`/`model_tables`).
- `PHYSICAL_MODELS` names exactly the base models passed to `.promise(...)`.
  Do **not** iterate `duckdb.model_tables`: it can include `.model(...)` views
  with neither `data/<view>/` nor a physical table.
- The connector config arrives in `secrets["csv_source"]` (delivered by the
  `csv-source` generic-secrets service). Never hard-code an absolute source
  path in the transform.
- Writes go **through the port**: `dlt.destinations.duckdb(credentials=duckdb.path)`
  + `dataset_name=duckdb.schema`. NEVER a raw `duckdb.connect(...)` write, never
  `CREATE TABLE` / `CREATE VIEW` DDL, never a hardcoded staging path.
- `write_disposition="replace"` — reruns must be idempotent, not duplicating.
- The read-back-and-assert block and the `.transform-complete` touch are
  MANDATORY, not decoration: the first enforces the naming invariant, the
  second is what the supervisor's readiness gate polls.

**Other connector types**: everything above is identical except the
`readers = [...]` body and the `secrets[...]` key — take those from `reference/`.

### Step 5 — `spec.py`: promises + transform + the `duckdb` output port

`spec.py` is the author-facing source of truth the supervisor compiles into
the deployment YAML. It declares the infra profile, wires the transform to the
local Python compute service, promises every physical base model on the DuckDB
storage output port, and registers each query-time semantic view.

Bind the three service references by relative infra-profile path (all three
resolve against `infra-profile.yaml`, Step 2):

```python
"""A desktop data product authored entirely in Python. The supervisor compiles
this to the kernel definition YAML at create time — never hand-write
deployment-spec / manifest / models YAML."""

from nxd.spec import data_product, data_product_output, script, storage

from models import customers, orders, order_metrics

_csv = "/infra-profile/desktop-local#/services/csv-source"
_compute = "/infra-profile/desktop-local#/services/python-compute"
_duckdb = "/infra-profile/desktop-local#/services/duckdb"

_output = (
    data_product_output()
    .promise(customers)
    .promise(orders)
    .model(order_metrics)
    .port("duckdb", storage(_duckdb))
)

spec = (
    data_product(
        name="<dp-name>",
        domain="desktop.local",
        version="0.0.1",
        infra_profile="desktop-local",
    )
    .transform(
        script("transform/main.py")
        .compute(_compute)
        .secrets([_csv])
    )
    .output(_output)
)
```

Contract facts baked into this shape — keep every one:

- **The output port is named `duckdb`** (`.port("duckdb", storage(...))`) — the
  local DuckDB storage driver requires that exact name, and the transform param
  matches it (Step 4). Never `"output"`.
- **`infra_profile="desktop-local"`** on `data_product(...)`, matching
  `infra-profile.yaml`'s `metadata.name`.
- **`script("transform/main.py")`**, not `code(transform)` — the desktop
  transform is a standalone entrypoint file the local Python compute driver
  executes; it registers itself via `@data_product.on_transform()`.
  `.compute(...)` binds the `python-compute` service; `.secrets([...])` delivers
  the `csv-source` connector config as the transform's `secrets` dict.
- Promise exactly the physical inferred models. Register every metric view via
  `.model(view)`, never `.promise(view)`: a view is query-time only and is not
  written by the transform.
- **No `.semantic_tools(...)`.** On desktop the semantic MCP catalog
  (`list_models`, `describe_model`, `semantic_model`, `run_semantic_query`) is
  built by the supervisor's semantic child reading the compiled model roles — it
  does NOT come from the spec. The
  proven closure serves all four tools with NO `.semantic_tools()` in the spec.
  `.semantic_tools()` emits a kernel RPC port that needs a live RPC driver — a
  k8s-topology artifact with no local RPC driver on desktop. Adding it here is
  wrong: it wires a port nothing serves. Leave it out.

**Other connector types**: only the variable name and its service path
(connector-types table above) change; for 2+ of one type, `.secrets([...])`
takes one labeled variable per instance — see `reference/multi-source.md`.

### Step 6 — `requirements.txt`: the proven pins

```
nxd.data_product[spec]
dlt[duckdb]==1.28.2
duckdb==1.5.4
pandas==2.3.3
```

`dlt[duckdb]==1.28.2` + `duckdb==1.5.4` are the pins proven against the S0
supervisor — do not float them. `pandas` is required by dlt's `read_csv`
transformer. Python `>=3.12,<3.13` is the proven interpreter range.

**Other connector types add to these pins, never replace them** — see
`reference/` for the exact per-type additions (Parquet extra, `dlt[sql_database]`
+ one vendor driver, or none for REST API).

### Step 7 — Self-check before handing off (MANDATORY)

Confirm the `duckdb` port/parameter pair and no `.semantic_tools(...)`. Then
walk the physical naming invariant (`models.py` == `.promise` ==
`PHYSICAL_MODELS` == the connector's per-model reference — see "THE NAMING
INVARIANT" table); `.model(...)` views deliberately have no such reference at
all. Confirm supplied CSVs are unchanged, then dry-run the transform against a
scratch DuckDB — the same execution the supervisor performs minus the kernel:

```python
# self_check.py — run from the closure root:
#   uv run --python 3.12 --with "dlt[duckdb]==1.28.2" --with "duckdb==1.5.4" \
#     --with "pandas==2.3.3" python self_check.py
import sys, tempfile, types
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class DuckDbOutput:
    path: str; schema: str; model_tables: dict; models: dict = field(default_factory=dict)

nxd = types.ModuleType("nxd"); core = types.ModuleType("nxd.core")
ctx = types.ModuleType("nxd.core.context"); ctx.DuckDbOutput = DuckDbOutput; dp = types.SimpleNamespace(
    on_transform=lambda *a, **k: (lambda fn: fn), main=lambda: None)
nxd.data_product, nxd.core, core.context = dp, core, ctx
sys.modules.update({"nxd": nxd, "nxd.core": core, "nxd.core.context": ctx})

sys.path.insert(0, ".")
from transform.main import PHYSICAL_MODELS, ingest  # noqa: E402

MODELS = [d.name for d in sorted(Path("data").iterdir()) if d.is_dir()]
assert set(PHYSICAL_MODELS) == set(MODELS), "physical models must match data/"
run = Path(tempfile.mkdtemp())
out = DuckDbOutput(path=str(run / "data.duckdb"), schema="main",
                   model_tables={m: m for m in MODELS})
ingest(duckdb=out, secrets={"csv_source": str(Path("data").resolve())})
import duckdb
con = duckdb.connect(out.path, read_only=True)
for m in MODELS:  # unquoted main.<name> — the invariant, physically
    print(m, con.execute(f"SELECT COUNT(*) FROM main.{m}").fetchone()[0])
assert (run / ".transform-complete").exists()
print("SELF-CHECK OK")
```
If the read-back assert in the transform fires, or an unquoted
`main.<name>` query fails, a name diverged somewhere — fix the NAME (across
`models.py`, `.promise`, and `data/<name>/`), never quote your way around it.

**Database/API connectors need live credentials to dry-run.** With
credentials, run each type's own connectivity check exactly as its reference
doc specifies — `database-source.md`'s asserts `row_count > 0` per model;
`api-source.md`'s asserts a parseable response per resource — never an exact
fixture count either way. Without credentials, report the connectivity
self-check as **not run** — never claim it passed.

---
## Invariants — NEVER violate these

- **Python-only closure**: emit `spec.py` + `models.py` + `infra-profile.yaml` + `transform/main.py` + `requirements.txt` + the connector-type-specific companion artifact (see the connector-types table in Overview). NEVER hand-write `deployment-spec.yaml` / `manifest.yaml` / `models.yaml` — the supervisor compiles those from the Python at pin time.
- **The naming invariant**: each physical base model name == `models.py` `semantic_model` arg == `spec.py` `.promise` == `PHYSICAL_MODELS` == the connector's per-model reference (see "THE NAMING INVARIANT" table) == `main.<name>`, unquoted lowercase snake_case. Semantic views are `.model(...)` only and have no physical table. The transform's read-back assert is the runtime tripwire — keep it.
- **Output port named `duckdb`**: `.port("duckdb", storage(...))`, transform param `duckdb` typed `DuckDbOutput` (port name == param name). The local DuckDB driver requires exactly this name.
- **Through the port, always**: dlt destination is `duckdb.path` / `duckdb.schema`. No raw `duckdb.connect` writes, no view/table DDL, no direct file writes into staging.
- **No `.semantic_tools(...)`**: the supervisor's semantic child builds the catalog from compiled semantic roles; the spec must not emit an RPC port.
- **Public semantic DSL only**: base models carry `primary_key` / `dimension` / `join`; metrics are `metric_field(metric(...))` on `semantic_view(...)`. Never import private modules or write metadata directly.
- **Validated base keys**: every promised physical model has one or more existing source columns marked `primary_key()`; their tuple is non-null and unique across the supplied export. Never synthesize a key, and stop for a source key when that evidence is absent.
- **Connector via secrets, `infra-profile.yaml` shape**: `metadata.name: desktop-local`, at least three services (`duckdb`, `python-compute`, one connector service per source instance, labeled when 2+ of a type — `reference/multi-source.md`), delivered via `.secrets([...])` on the transform. `duckdb`, `python-compute`, `csv-source`, and `file-source` keep `attributes: []`; `db-source`/`api-source` (and their labeled variants) carry one `{"key": ..., "value": ..., "public": false}` attribute per real credential field instead — see `reference/database-source.md` / `reference/api-source.md`. Never fabricate a credential, never narrate one in chat, and never let two same-type instances share a name.
- **Run-local dlt state** (`pipelines_dir` under the run dir + `DLT_DATA_DIR` set; never `~/.dlt`); **`write_disposition="replace"`**; **`.transform-complete` touch** after the assert.
- **Place, don't redesign**: semantic roles come from nxd-semantic-data-product. Preserve a file connector's supplied export exactly, and treat a database or API connector as read-only; use an existing validated key or surface the missing-key problem. Promise only base models, register metric views with `.model(...)`, and add no marker model on desktop.
- **Proven pins**: `dlt[duckdb]==1.28.2`, `duckdb==1.5.4`, pandas, the nxd wheel; Python `>=3.12,<3.13`.
## Related skills

| Skill | Relationship |
|---|---|
| `nxd-semantic-data-product` | Produces the inferred semantic model this skill places; owns the role grammar and the k8s `.semantic_tools()` topology |
| `nxd-data-product-builder` | The k8s/cloud DP authoring path (Snowflake et al.) — use it, not this skill, off-desktop |
