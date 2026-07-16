---
name: nxd-generate-dp
description: Generates the COMPLETE runnable data-product closure for lean-desktop Nextdata OS (the S0 desktop supervisor) from a natural-language intent, an inferred semantic model, and a connector config — spec.py + models.py + transform/main.py + requirements + the deployment-spec/manifest/models.yaml port-and-executor wiring, ready to boot locally and produce a queryable DuckDB result. Use when the task is to "generate a data product", "build a DP from intent", "assemble a runnable data product around an inferred semantic model", or to turn a CSV/file connector export plus stakeholder questions into a local desktop data product. Pairs with nxd-semantic-data-product — that skill INFERS the semantic model (the __nxd_semantic__ blobs); this skill PLACES it and assembles the full closure around it. Not for the k8s/Snowflake topology — use nxd-data-product-builder / nxd-semantic-data-product directly there.
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
  version: 0.9.1
---

# nxd-generate-dp skill

## Overview

This skill assembles the **complete runnable definition closure** for a local
(desktop) data product from three inputs:

1. **Intent** — the user's natural-language description of what the DP is for.
2. **Inferred semantic model** — the per-column role blobs
   (`__nxd_semantic__` grammar) produced by the **nxd-semantic-data-product**
   skill's inference mode (its `schema.json` profile + role declarations).
   That skill designs the blobs; this skill places them. Do not redesign them.
3. **Connector config** — where the source data lives. The proven S0 connector
   is a local CSV export: one subdirectory per table, `*.csv` inside.

The output is a directory the **desktop supervisor** can pin, boot, and
publish: the supervisor snapshots the closure, boots the local kernel, runs
the transform (dlt through the DuckDB output port), verifies staging, promotes
the artifact, and stands up the semantic MCP endpoint over it.

## The closure layout

```
<dp-root>/
├── spec.py                # author-facing definition: promises + .semantic_tools()
├── models.py              # semantic models + placed __nxd_semantic__ blobs
├── transform/
│   └── main.py            # the dlt-through-port ingest (standalone entrypoint)
├── requirements.txt       # proven pins (below)
├── deployment-spec.yaml   # services: DuckDB storage output + generic-secrets
├── manifest.yaml          # executor (Python compute) + output port config
├── models.yaml            # promised models + attributes (kernel-parsed)
├── csv-source-path        # one line: relative path to the CSV export root
└── data/                  # the connector export: data/<model>/*.csv
    └── <model>/…
```

The supervisor's snapshot pins `deployment-spec.yaml`, `manifest.yaml`,
`models.yaml`, the `transform/` and `data/` directories, and
`csv-source-path`. `spec.py` and `models.py` are the author-facing source of
truth the YAML wiring is derived from — generate BOTH and keep them
consistent (the desktop toolchain will compile spec → YAML; until then you
materialize the YAMLs yourself, exactly in the shapes below).

> Layout note: unlike the k8s `.semantic_tools()` topology (modules flat at
> the DP root, no subdir), the desktop closure keeps the transform at
> `transform/main.py` — that is the directory the snapshot pins and the local
> Python compute driver executes.

---

## THE NAMING INVARIANT (the correctness spine — protect it everywhere)

One lowercase, unquoted, snake_case name per model, agreed on by **five
surfaces**:

| Surface | Where the name appears |
|---|---|
| `models.py` | `semantic_model("<name>")` |
| `models.yaml` | `models[].name: <name>` |
| `manifest.yaml` | `model_tables: {<name>: <name>}` — key AND value, identity |
| `data/` | the connector subdirectory `data/<name>/` |
| the physical table | what dlt writes: `main.<name>` |

`.model(name)` == `main.<name>` == the dlt-written table, **unquoted
lowercase**. dlt lowercases/snake_cases whatever it is given, so any
prettified or cased name silently diverges from the promise — which is why
the generated transform MUST read back what dlt produced and assert it
matches `model_tables` (see the template). Attribute names are byte-exact
copies of the CSV headers (post-dlt snake_case), in `models.py` and
`models.yaml` alike.

---

## Workflow

### Step 1 — Collect the three inputs

- The intent tells you the DP `name`, description, and which questions the
  semantic layer must answer.
- The inferred model (from nxd-semantic-data-product) gives you, per model:
  the grain, dimensions, metrics, joins, PII flags — as ready
  `__nxd_semantic__` blobs — plus each column's data type.
- The connector config gives you the CSV export root. Confirm the layout is
  one subdirectory per model (`<root>/<model>/*.csv`) and read each header:
  those headers are the attribute vocabulary. If a model in the inferred
  model has no matching data subdirectory (or vice versa), stop and surface
  it — do not invent or drop models.

### Step 2 — `models.py`: place the inferred blobs

Follow the **nxd-semantic-data-product** skill's Step 2 pattern (the
`_annotate()` stopgap writing `AttributeSpec._metadata["__nxd_semantic__"]`)
— reference that skill for the role grammar. Here you only PLACE:

- `semantic_model("<name>")` — the bare lowercase physical table name.
- One `AttributeSpec(name="<column>", data_type=...)` per CSV header column,
  byte-exact, all of them (unannotated columns still get an AttributeSpec —
  they must reach `models.yaml`).
- The provided blob on each role-bearing column, **verbatim** — multi-role
  `{"roles": [...]}` wrappers included. Columns the inferred model left
  unannotated stay unannotated (do not add metrics no question motivated).
- No marker model: desktop produce-verification is the transform's
  `.transform-complete` file, not a marker row.

Data-type mapping (inferred type → `nxd.spec.data_types` / `models.yaml`):

| Inferred | `models.py` | `models.yaml` `data-type` |
|---|---|---|
| string | `string()` | `string` |
| int | `int64()` | `int` |
| number / double / float | `float64()` | `number` / `double` / `float` |
| bool | `boolean()` | `bool` |
| date | `date32()` | `date` |

### Step 3 — `transform/main.py`: the dlt-through-port ingest

This is the proven shape. The transform receives the typed **output port
handle** (`DuckDbOutput`: `path`, `schema`, `model_tables`) and the secrets
dict (the connector config), streams each model's CSV directory through dlt
into the port's DuckDB file, then **reads back and asserts** the produced
table names. Parameterize nothing but the docstring — the model list comes
from `output.model_tables` at runtime, so the same transform body serves any
model set.

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
def ingest(output: DuckDbOutput, secrets: dict[str, Any]) -> None:
    """Stream each model's CSV directory into the DuckDB output port."""
    source_root = Path(secrets["csv_source"])
    # Keep ALL dlt state run-local (next to the staging file) — never ~/.dlt.
    run_dir = Path(output.path).parent
    pipelines_dir = run_dir / "dlt-pipelines"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DLT_DATA_DIR"] = str(run_dir / "dlt-data")

    pipeline = dlt.pipeline(
        pipelines_dir=str(pipelines_dir),
        destination=dlt.destinations.duckdb(credentials=output.path),
        dataset_name=output.schema,
    )
    readers = []
    for model, table_name in output.model_tables.items():
        reader = filesystem(
            bucket_url=str(source_root / model), file_glob="*.csv"
        ) | read_csv()
        readers.append(reader.with_name(table_name))
    pipeline.run(readers, write_disposition="replace")

    # THE NAMING INVARIANT: what dlt wrote must be exactly the promised
    # tables. dlt snake_cases/lowercases names — catch any divergence HERE,
    # not at query time.
    actual = set(pipeline.default_schema.data_table_names())
    expected = set(output.model_tables.values())
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

- The transform param is named **`output`** — it MUST match the manifest port
  name (`output.ports.output`), and it MUST be typed `DuckDbOutput` (an
  untyped param gets a raw context with no `path`/`model_tables`).
- The connector config arrives in `secrets["csv_source"]` (delivered by the
  `csv-source` generic-secrets service). Never hard-code an absolute source
  path in the transform.
- Writes go **through the port**: `dlt.destinations.duckdb(credentials=output.path)`
  + `dataset_name=output.schema`. NEVER `duckdb.connect(...)` writes, never
  `CREATE TABLE` / `CREATE VIEW` DDL, never a hardcoded staging path.
- `write_disposition="replace"` — reruns must be idempotent, not duplicating.
- The read-back-and-assert block and the `.transform-complete` touch are
  MANDATORY, not decoration: the first enforces the naming invariant, the
  second is what the supervisor's readiness gate polls.

### Step 4 — `spec.py`: promises + `.semantic_tools()`

Reuse the nxd-semantic-data-product spec pattern (promise every annotated
model, one `.semantic_tools(service=...)`, never `data_product_rpc_output()`).
Desktop differences: the storage port is the local DuckDB `output` service,
and there is **no `code(transform)` wiring** — on desktop the executor is
declared in `manifest.yaml` (Python compute) and the transform registers
itself via `@data_product.on_transform()`.

```python
"""Author-facing definition. The desktop supervisor consumes the YAML
materialization of this spec (deployment-spec/manifest/models.yaml); keep
them in lockstep."""

from nxd.spec import data_product, data_product_output, storage

from models import customers, orders   # every inferred model

_storage = (
    data_product_output()
    .promise(customers)
    .promise(orders)
    .port("output", storage("/infra-profile/desktop-local#/services/output"))
)

spec = (
    data_product(
        name="<dp-name>",
        domain="desktop.local",
        version="0.0.1",
    )
    .output(_storage)
    # ONE line — the four governed MCP tools (list_models, semantic_model,
    # describe_model, run_semantic_query) over the placed annotations.
    .semantic_tools(service="mcp-api")
)
```

Promise **exactly** the inferred models — an un-promised model never reaches
the manifest; an extra invented one breaks the closure-wide name agreement.

### Step 5 — The wiring YAMLs (the shapes S0 pins — match them exactly)

`deployment-spec.yaml` — two services, these driver ids:

```yaml
environment: desktop
infraProfile: in-memory
services:
  - driver: nxd:local/duckdb/storage:0.1.0
    environment: desktop
    infraService: output
    name: output
  - driver: nxd:generic-secrets:1.0.0
    environment: desktop
    infraService: csv-source
    name: csv-source
```

`manifest.yaml` — executor + the output port. `model_tables` is the
**identity map** over the model names (the invariant, surface #3):

```yaml
domain: desktop.local
inputs: {}
name: <dp-name>
executor:
  driver: nxd:local/python/compute:0.1.0
  secrets:
    - csv-source
output:
  ports:
    output:
      service: output
      config:
        model_tables:
          customers: customers
          orders: orders
        path: __NXD_STAGING_DATA__
        schema: main
version: 0.0.1
```

`__NXD_STAGING_DATA__` is a **verbatim placeholder** — the supervisor
substitutes the per-run staging path when it pins the snapshot. Writing a
real path there breaks pinning; the snapshot step hard-fails if the
placeholder is missing. `schema` is `main` (DuckDB's default schema — the
`main.<name>` half of the invariant).

`models.yaml` — every promised model, every CSV-header column, byte-exact:

```yaml
api-version: data-product.nextdata.com/v1
models:
  - name: customers
    description: One row per customer.
    attributes:
      customer_id:
        data-type: string
      is_churned:
        data-type: bool
      # ... every header column, byte-exact names
```

`csv-source-path` — one line, the **relative** path from the closure root to
the CSV export root (e.g. `data`). The supervisor resolves it inside the
pinned snapshot; an absolute path escapes the snapshot and fails.

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

Walk the naming invariant across all five surfaces and confirm byte-equality,
then dry-run the transform against a scratch DuckDB — the same execution the
supervisor performs, minus the kernel:

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
ingest(output=out, secrets={"csv_source": str(Path("data").resolve())})
import duckdb
con = duckdb.connect(out.path, read_only=True)
for m in MODELS:  # unquoted main.<name> — the invariant, physically
    print(m, con.execute(f"SELECT COUNT(*) FROM main.{m}").fetchone()[0])
assert (run / ".transform-complete").exists()
print("SELF-CHECK OK")
```

If the read-back assert in the transform fires, or an unquoted
`main.<name>` query fails, a name diverged somewhere — fix the NAME (all five
surfaces), never quote your way around it.

---

## Invariants — NEVER violate these

- **The naming invariant**: model name == `models.yaml` name ==
  `model_tables` key == `model_tables` value == `data/<name>/` ==
  `main.<name>`, unquoted lowercase snake_case. The transform's
  read-back-assert stays in — it is the invariant's runtime tripwire.
- **Through the port, always**: dlt destination is `output.path` /
  `output.schema`. No `duckdb.connect` writes, no view or table DDL, no
  direct file writes into staging.
- **`__NXD_STAGING_DATA__` verbatim** in `manifest.yaml`; `schema: main`.
- **Connector via secrets**: source root only from `secrets["csv_source"]`;
  `csv-source-path` is relative; the generic-secrets service is named
  `csv-source` and listed under `executor.secrets`.
- **Transform param named `output`, typed `DuckDbOutput`** — port name ==
  param name.
- **Run-local dlt state**: `pipelines_dir` under the run dir +
  `DLT_DATA_DIR` set. Never pollute `~/.dlt`.
- **`write_disposition="replace"`** — reruns replace, never append.
- **`.transform-complete` touch** after the assert passes.
- **Place, don't redesign**: the semantic blobs come from
  nxd-semantic-data-product verbatim; promise exactly those models; no
  marker model on desktop.
- **Proven pins**: `dlt[duckdb]==1.28.2`, `duckdb==1.5.4`, pandas, the nxd
  wheel; Python `>=3.12,<3.13`.

---

## Related skills

| Skill | Relationship |
|---|---|
| `nxd-semantic-data-product` | Produces the inferred semantic model this skill places; owns the role grammar, `_annotate()` stopgap, and the k8s `.semantic_tools()` topology |
| `nxd-data-product-builder` | The k8s/cloud DP authoring path (Snowflake et al.) — use it, not this skill, off-desktop |
| `nxd-data-product-query` | Consumes the deployed DP's semantic MCP tools |
