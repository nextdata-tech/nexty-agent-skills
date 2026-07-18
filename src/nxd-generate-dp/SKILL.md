---
name: nxd-generate-dp
description: Generates the COMPLETE runnable Python-only data-product closure for lean-desktop Nextdata OS (the desktop supervisor) from a natural-language intent, an inferred semantic model, and a connector config — spec.py + models.py + infra-profile.yaml + transform/main.py + requirements + the CSV export, ready to boot locally and produce a queryable DuckDB result. The supervisor compiles spec.py into the kernel definition YAML at create time, so the author never hand-writes deployment-spec / manifest / models YAML. Use when the task is to "generate a data product", "build a DP from intent", "assemble a runnable data product around an inferred semantic model", or to turn a connector export plus stakeholder questions into a local desktop DP. Pairs with nxd-semantic-data-product, which INFERS the semantic model this skill PLACES and assembles the closure around. Not for the k8s/Snowflake topology — use nxd-data-product-builder there.
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
  version: 0.10.0
---

# nxd-generate-dp skill

## Overview

This skill assembles the **complete Python-only definition closure** for a
local (desktop) data product from three inputs:

1. **Intent** — the user's natural-language description of what the DP is for.
2. **Inferred semantic model** — the per-column semantic roles produced by the
   **nxd-semantic-data-product** skill's inference mode (its `schema.json`
   profile + role declarations). That skill designs the roles; this skill
   places them. Do not redesign them.
3. **Connector config** — where the source data lives. The proven desktop
   connector is a local CSV export: one subdirectory per table, `*.csv` inside.

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

**The author NEVER writes `deployment-spec.yaml`, `manifest.yaml`, or
`models.yaml`.** Those three are now compiled by the desktop supervisor from
`spec.py` + `models.py` when it creates and pins the DP. Emitting them by hand
is wrong — the supervisor owns their shape and will overwrite them. Your
source of truth is the Python: get `spec.py` and `models.py` right and the
compiled YAML follows.

> Layout note: unlike the k8s `.semantic_tools()` topology (modules flat at
> the DP root, no subdir), the desktop closure keeps the transform at
> `transform/main.py` — that is the directory the snapshot pins and the local
> Python compute driver executes. `models.py` and `spec.py` sit at the root and
> are imported by the compiler.

---

## THE NAMING INVARIANT (the correctness spine — protect it everywhere)

One lowercase, unquoted, snake_case name per model, agreed on by **three
authored surfaces** (the supervisor derives the compiled-YAML `models.yaml`
name and the `model_tables` identity map from these — you do not author them):

| Surface | Where the name appears |
|---|---|
| `models.py` | `semantic_model("<name>")` |
| `spec.py` | `.promise(<name>)` — imported from `models` |
| `data/` | the connector subdirectory `data/<name>/` |
| the physical table | what dlt writes: `main.<name>` |

`.model(name)` == `main.<name>` == the dlt-written table, **unquoted
lowercase**. dlt lowercases/snake_cases whatever it is given, so any
prettified or cased name silently diverges from the promise — which is why
the generated transform MUST read back what dlt produced and assert it
matches the port's `model_tables` (see the template). Attribute names are
byte-exact copies of the CSV headers (post-dlt snake_case) in `models.py`.

Separately, the **storage output port MUST be named `duckdb`** — the local
DuckDB storage driver requires that exact port name, and the transform param
name must match it (see Step 3). `output` is wrong; use `duckdb`.

---

## Workflow

### Step 1 — Collect the three inputs

- The intent tells you the DP `name`, description, and which questions the
  semantic layer must answer.
- The inferred model (from nxd-semantic-data-product) gives you, per model:
  the primary key, dimensions, joins, PII flags — plus each column's data
  type. (Metrics are consume-time / view-level and are NOT placed on base
  model fields — see Step 2.)
- The connector config gives you the CSV export root. Confirm the layout is
  one subdirectory per model (`<root>/<model>/*.csv`) and read each header:
  those headers are the attribute vocabulary. If a model in the inferred
  model has no matching data subdirectory (or vice versa), stop and surface
  it — do not invent or drop models.

### Step 2 — `models.py`: place the inferred roles with the public DSL

Author `models.py` with the **real public semantic DSL** — NOT the
`_annotate()` private-metadata stopgap. Import the role builders and wrap each
field:

```python
from nxd.spec import semantic_model
from nxd.spec.data_types import number, string
from nxd.spec import field, primary_key, dimension, join
```

Here you only PLACE:

- `semantic_model("<name>")` — the bare lowercase physical table name.
- `.schema({...})` mapping each CSV header column (byte-exact) to a typed
  value. A column that carries a semantic role is authored as
  `field(<type>(), <role>())`; a column with no role is authored as the bare
  type (`"country": string()`), so it still reaches the compiled schema.
- One role per role-bearing base field. **Base models carry ONLY
  `primary_key()`, `dimension(...)`, or `join(...)`.** Metrics are consume-time
  / view-level — the DSL RAISES if you attach a metric to a base-model field,
  so never place one here.

Role builders (verified DSL facts):

| Role | Form |
|---|---|
| primary key | `field(number(), primary_key())` — the entity key. Emit `primary_key()`; NEVER the deprecated `grain` alias. |
| dimension | `field(string(), dimension(name="<concept>", label="<label>"))` |
| join (N:1) | `field(number(), join(to="<model>", to_column="<col>"))` — note `to=` and `to_column=`, NOT `to_model=` |

Columns the inferred model left unannotated stay bare-typed (do not invent
roles no question motivated). No marker model: desktop produce-verification is
the transform's `.transform-complete` file, not a marker row.

Worked example (matches the proven closure):

```python
"""Semantic models for the desktop DP. Fields carry only the base-model roles
the DSL allows (primary_key, dimension, join); metrics are consume-time."""

from nxd.spec import semantic_model
from nxd.spec.data_types import number, string
from nxd.spec import field, primary_key, dimension, join

customers = semantic_model("customers").schema(
    {
        "customer_id": field(number(), primary_key()),
        "country_id": field(
            string(),
            dimension(name="customer_country", label="country"),
        ),
        "country": string(),
    }
)

orders = semantic_model("orders").schema(
    {
        "order_id": field(number(), primary_key()),
        "customer_id": field(
            number(),
            join(to="customers", to_column="customer_id"),
        ),
        "amount": number(),
    }
)
```

Data-type mapping (inferred type → `nxd.spec.data_types`):

| Inferred | `models.py` |
|---|---|
| string | `string()` |
| int / number | `number()` |
| number / double / float | `number()` |
| bool | `boolean()` |
| date | `date32()` |

### Step 3 — `transform/main.py`: the dlt-through-port ingest

This is the proven shape. The transform receives the typed **output port
handle** (`DuckDbOutput`: `path`, `schema`, `model_tables`) and the secrets
dict (the connector config), streams each model's CSV directory through dlt
into the port's DuckDB file, then **reads back and asserts** the produced
table names. The handle param is named **`duckdb`** — it MUST match the
storage output port name (`duckdb`, from Step 4). Parameterize nothing but the
docstring — the model list comes from `duckdb.model_tables` at runtime, so the
same transform body serves any model set.

```python
"""<dp-name>: load the CSV connector export into the local DuckDB output port."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# S0 source-checkout shim: when the desktop supervisor runs this transform
# against a checkout (interpreter without the nxd wheel), it exports
# NXD_DESKTOP_REPO_ROOT; put the local nxd packages on sys.path. With the
# wheel installed (requirements.txt) the guard is a no-op. Keep it GUARDED —
# an unguarded os.environ["..."] lookup crashes every non-supervisor run.
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
    for model, table_name in duckdb.model_tables.items():
        reader = filesystem(
            bucket_url=str(source_root / model), file_glob="*.csv"
        ) | read_csv()
        readers.append(reader.with_name(table_name))
    pipeline.run(readers, write_disposition="replace")

    # THE NAMING INVARIANT: what dlt wrote must be exactly the promised
    # tables. dlt snake_cases/lowercases names — catch any divergence HERE,
    # not at query time.
    actual = set(pipeline.default_schema.data_table_names())
    expected = set(duckdb.model_tables.values())
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

### Step 4 — `spec.py`: promises + transform + the `duckdb` output port

`spec.py` is the author-facing source of truth the supervisor compiles into
the deployment YAML. It declares the infra profile, wires the transform to the
local Python compute service, and promises every inferred model on the DuckDB
storage output port.

Bind the three service references by relative infra-profile path (all three
resolve against `infra-profile.yaml`, Step 5):

```python
"""A desktop data product authored entirely in Python. The supervisor compiles
this to the kernel definition YAML at create time — never hand-write
deployment-spec / manifest / models YAML."""

from nxd.spec import data_product, data_product_output, script, storage

from models import customers, orders   # every inferred model

_csv = "/infra-profile/desktop-local#/services/csv-source"
_compute = "/infra-profile/desktop-local#/services/python-compute"
_duckdb = "/infra-profile/desktop-local#/services/duckdb"

_output = (
    data_product_output()
    .promise(customers)
    .promise(orders)
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
  matches it (Step 3). Never `"output"`.
- **`infra_profile="desktop-local"`** on `data_product(...)`, matching
  `infra-profile.yaml`'s `metadata.name`.
- **`script("transform/main.py")`**, not `code(transform)` — the desktop
  transform is a standalone entrypoint file the local Python compute driver
  executes; it registers itself via `@data_product.on_transform()`.
  `.compute(...)` binds the `python-compute` service; `.secrets([...])` delivers
  the `csv-source` connector config as the transform's `secrets` dict.
- Promise **exactly** the inferred models — an un-promised model never reaches
  the compiled manifest; an extra invented one breaks the closure-wide name
  agreement.
- **No `.semantic_tools(...)`.** On desktop the semantic MCP catalog
  (`list_models`, `describe_model`, `semantic_model`, `run_semantic_query`) is
  built by the supervisor's semantic child reading the compiled `models.yaml`
  `__nxd_semantic__` annotations directly — it does NOT come from the spec. The
  proven closure serves all four tools with NO `.semantic_tools()` in the spec.
  `.semantic_tools()` emits a kernel RPC port that needs a live RPC driver — a
  k8s-topology artifact with no local RPC driver on desktop. Adding it here is
  wrong: it wires a port nothing serves. Leave it out.

### Step 5 — `infra-profile.yaml`: the desktop-local profile (emitted prerequisite)

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
- Three services, each with `attributes: []`: `duckdb` (local DuckDB storage,
  the output port backend), `python-compute` (local Python compute, runs the
  transform), `csv-source` (generic-secrets, delivers the CSV export root).

Finally, the closure also carries **`csv-source-path`** — one line, the
**relative** path from the closure root to the CSV export root (e.g. `data`).
The supervisor resolves it inside the pinned snapshot; an absolute path escapes
the snapshot and fails.

> The supervisor compiles `deployment-spec.yaml`, `manifest.yaml`, and
> `models.yaml` from `spec.py` + `models.py` at pin time — including the
> `model_tables` identity map, the staging-path placeholder, and the
> `__nxd_semantic__` annotations the semantic child reads. **You never write
> those three files.**

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

### Step 7 — Self-check before handing off (MANDATORY)

First confirm the two spec invariants: the output port is named `duckdb`
(`.port("duckdb", ...)` in `spec.py`, param `duckdb` in the transform) and
`spec.py` has **no `.semantic_tools(...)` call**. Then walk the naming
invariant across the authored surfaces (`models.py` name == `.promise` ==
`data/<name>/`) and confirm byte-equality, then dry-run the transform against a
scratch DuckDB — the same execution the supervisor performs, minus the kernel:

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
ctx = types.ModuleType("nxd.core.context"); ctx.DuckDbOutput = DuckDbOutput
dp = types.SimpleNamespace(
    on_transform=lambda *a, **k: (lambda fn: fn), main=lambda: None)
nxd.data_product, nxd.core, core.context = dp, core, ctx
sys.modules.update({"nxd": nxd, "nxd.core": core, "nxd.core.context": ctx})

sys.path.insert(0, ".")
from transform.main import ingest  # noqa: E402

MODELS = [d.name for d in sorted(Path("data").iterdir()) if d.is_dir()]
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

---

## Invariants — NEVER violate these

- **Python-only closure**: emit `spec.py` + `models.py` + `infra-profile.yaml` + `transform/main.py` + `requirements.txt` + `csv-source-path` + `data/`. NEVER hand-write `deployment-spec.yaml` / `manifest.yaml` / `models.yaml` — the supervisor compiles those from the Python at pin time.
- **The naming invariant**: model name == `models.py` `semantic_model` arg == `spec.py` `.promise` == `data/<name>/` == `main.<name>`, unquoted lowercase snake_case. The transform's read-back-assert is the runtime tripwire — keep it.
- **Output port named `duckdb`**: `.port("duckdb", storage(...))`, transform param `duckdb` typed `DuckDbOutput` (port name == param name). The local DuckDB driver requires exactly this name.
- **Through the port, always**: dlt destination is `duckdb.path` / `duckdb.schema`. No raw `duckdb.connect` writes, no view/table DDL, no direct file writes into staging.
- **No `.semantic_tools(...)`**: the supervisor's semantic child builds the catalog from the compiled `__nxd_semantic__` annotations; the spec must not emit an RPC port.
- **Base models carry only `primary_key` / `dimension` / `join`**: emit `primary_key()` (never the deprecated `grain` alias); a metric on a base field makes the DSL raise (metrics are consume-time).
- **Connector via secrets**: source root only from `secrets["csv_source"]`; `csv-source-path` relative; the generic-secrets service is named `csv-source`, delivered via `.secrets([...])` on the transform.
- **`infra-profile.yaml`**: `metadata.name: desktop-local`, three services (`duckdb`, `python-compute`, `csv-source`), each `attributes: []`.
- **Run-local dlt state** (`pipelines_dir` under the run dir + `DLT_DATA_DIR` set; never `~/.dlt`); **`write_disposition="replace"`**; **`.transform-complete` touch** after the assert.
- **Place, don't redesign**: semantic roles come from nxd-semantic-data-product; promise exactly those models; no marker model on desktop.
- **Proven pins**: `dlt[duckdb]==1.28.2`, `duckdb==1.5.4`, pandas, the nxd wheel; Python `>=3.12,<3.13`.

---

## Related skills

| Skill | Relationship |
|---|---|
| `nxd-semantic-data-product` | Produces the inferred semantic model this skill places; owns the role grammar and the k8s `.semantic_tools()` topology |
| `nxd-data-product-builder` | The k8s/cloud DP authoring path (Snowflake et al.) — use it, not this skill, off-desktop |
| `nxd-data-product-query` | Consumes the deployed DP's semantic MCP tools |
