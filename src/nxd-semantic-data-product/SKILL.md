---
name: nxd-semantic-data-product
description: Builds a governed text-to-SQL / metrics / semantic-layer data product on Nextdata OS, exposing curated metrics and dimensions over MCP so an AI agent can answer natural-language questions without writing raw SQL. Use when the task is to create or extend a data product that lets agents query business metrics by name (e.g. order_count, revenue) sliced by dimensions (e.g. region, product_category), when you need NL-to-SQL governance over a Snowflake data product, or when exposing a semantic layer as an MCP server tool set. The author writes only per-field semantic annotations on the models; the one-line .semantic_tools() spec flag auto-generates the four governed MCP tools from the installed nxd.data_product wheel (nxd.experimental.semantic) — imported, not vendored.
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
  version: 0.8.0
---

# nxd-semantic-data-product skill

## Overview

A semantic-layer data product exposes **named metrics and dimensions** over MCP.
An AI agent calls `run_semantic_query` with concept names; the data product
compiles a correct, governed SQL query and returns rows — no raw SQL escapes the
DP boundary.

**You author only the per-field semantic annotations on the models.** A single
`.semantic_tools(service=...)` flag on the spec auto-generates the four governed
MCP tools at pod boot. The kernel compiles the annotations into typed payloads;
the compiler, dialect, and tool factory ship in the `nxd.data_product` wheel as
`nxd.experimental.semantic` — imported, not vendored.

The four auto-generated tools:

| Tool | Purpose |
|------|---------|
| `list_models` | Enumerate the semantic models (entities) with grain + metric/dimension counts |
| `semantic_model` | Return one model's full registry projection (raw metrics/dimensions/joins) |
| `describe_model` | Human-oriented detail for one model: metrics (+ compatible dimensions), dimensions (+ PII flags), joins |
| `run_semantic_query` | Compile a concept selection to governed SQL, run it, return rows |

See `reference/overview.md` for the design and how annotations flow to the tools.

> **This skill teaches the `.semantic_tools()` pattern.** It
> replaces the older hand-wired `registry.py` + `tools.py` + `provision.py` +
> `data_product_rpc_output()` 4-tool loop. If you find a DP on the old pattern,
> migrate it (see "Migrating an old-pattern DP" below).

---

## Workflow

### Step 1 — Derive the semantic vocabulary from the schema

Interview the user or read the table DDL to establish, per source table:

1. **Model** — the physical table. A unique name + the **grain** column (the
   entity key, e.g. `order_id`) + an optional description.
2. **Dimensions** — columns an agent can group or filter by. Each: a concept
   `name`, the physical `column` it lives on, a logical `type`
   (`string` / `date` / `number`), a `description`, and `pii: true` if governed.
3. **Metrics** — named aggregated measures. Each: a concept `name`, the physical
   `column` it aggregates, the `agg` function
   (`count`, `count_distinct`, `sum`, `avg`, `min`, `max`), a `description`, and
   `boolean: true` if the column is a flag that counts truthy rows.
4. **Joins** — documented N:1 relationships. Each: declared on the MANY-side
   model's join key, naming `to_model` (the ONE side), `to_column`, and
   `cardinality: many_to_one`. Cross-model dimension reach is **auto-derived**
   from N:1 joins by the compiler.

### Step 2 — Author `models.py` with per-field `__nxd_semantic__` annotations

The semantic vocabulary is declared as a reserved `__nxd_semantic__` JSON blob on
each model attribute. The kernel reads those blobs from every **promised** model's
manifest, compiles them into a typed `SemanticRegistry`, and delivers the result
to the pod at boot as `<root>/.nxd/semantic/<model>.json`. The runtime rebuilds
the four tools from those payloads.

> **STOPGAP — the public author API is not yet available.** `AttributeSpec` has no public
> `.semantic_annotation()` setter, so the blob is injected by writing the
> **private** `_metadata` dict directly via an `_annotate()` helper. This is the
> only mechanism available until a public `AttributeSpec.semantic_annotation()` API
> ships. Keep the injection
> isolated to `models.py` and clearly marked; replace `_annotate()` with the
> public setter once it ships. Verify its status before publishing — if a
> public `AttributeSpec.semantic_annotation(blob)` exists in your wheel, use it.

Keep every module **flat at the DP root** — `models.py`, `transform.py`,
`spec.py` are siblings. No `transform/` subdir package.

```python
# models.py
import json

from nxd.spec import semantic_model
from nxd.spec._model import AttributeSpec
from nxd.spec.data_types import float64, int64, string

_SEMANTIC_KEY = "__nxd_semantic__"


def _annotate(attr: AttributeSpec, role: dict) -> AttributeSpec:
    """Inject a __nxd_semantic__ blob (stopgap — replace with the public
    AttributeSpec.semantic_annotation() once it ships)."""
    attr._metadata[_SEMANTIC_KEY] = json.dumps(role, separators=(",", ":"))
    return attr


orders = (
    semantic_model("orders")
    .description("One row per order.")
    .schema(
        {
            "ORDER_ID": _annotate(
                AttributeSpec(name="ORDER_ID", data_type=int64()),
                {"kind": "grain"},
            ),
            "REGION": _annotate(
                AttributeSpec(name="REGION", data_type=string(),
                              _description="Sales region."),
                {"kind": "dimension", "name": "region",
                 "description": "Sales region.", "type": "string"},
            ),
            # Multi-role: join key (N:1) AND a count_distinct metric.
            "PRODUCT_ID": _annotate(
                AttributeSpec(name="PRODUCT_ID", data_type=int64()),
                {"roles": [
                    {"kind": "join", "to_model": "products",
                     "to_column": "PRODUCT_ID", "cardinality": "many_to_one"},
                ]},
            ),
            "REVENUE_USD": _annotate(
                AttributeSpec(name="REVENUE_USD", data_type=float64(),
                              _description="Order revenue in USD."),
                {"kind": "metric", "name": "revenue", "agg": "sum",
                 "description": "Total revenue in USD."},
            ),
        }
    )
)

# COUNT on the grain column — patch a full roles list post-hoc (the bare
# {"kind": ...} shorthand has no inline multi-role form; the roles list REPLACES
# the bare-grain blob).
_annotate(
    orders._attributes["ORDER_ID"],
    {"roles": [
        {"kind": "grain"},
        {"kind": "metric", "name": "order_count", "agg": "count_distinct",
         "description": "Distinct orders placed."},
    ]},
)
```

**Role grammar** (one blob per column):

| Role | Blob |
|------|------|
| grain | `{"kind": "grain"}` |
| dimension | `{"kind": "dimension", "name": ..., "description": ..., "type": ..., "pii": <bool?>}` |
| metric | `{"kind": "metric", "name": ..., "agg": "count\|count_distinct\|sum\|avg\|min\|max", "description": ..., "boolean": <bool?>}` |
| join | `{"kind": "join", "to_model": ..., "to_column": ..., "cardinality": "many_to_one"}` |
| multi-role | `{"roles": [ {...}, {...} ]}` |

See `reference/registry-authoring.md` for the full role vocabulary, the
auto-derivation rules, and a worked generic example.

### Step 3 — Author `transform.py` to seed the base tables (no DDL view)

The tools query **base tables** directly — `run_semantic_query` compiles governed
SQL against them from the kernel payloads. There is **no semantic-view DDL** and
**no `@on_provision` hook** in this pattern. The transform's job is to seed the
base tables (and a one-row marker so the storage port's produce-verification
passes).

```python
# transform.py
from nxd.data_product.context import Snowflake


def transform(snowflake: Snowflake) -> None:
    import pandas as pd
    from snowflake import connector
    from snowflake.connector.pandas_tools import write_pandas

    if snowflake is None or not snowflake.schema:
        return
    fqn = (f"{snowflake.database}.{snowflake.schema}."
           if snowflake.database else f"{snowflake.schema}.")

    rows = pd.DataFrame([
        {"ORDER_ID": 101, "REGION": "EMEA", "PRODUCT_ID": 1, "REVENUE_USD": 100.0},
        {"ORDER_ID": 102, "REGION": "AMER", "PRODUCT_ID": 2, "REVENUE_USD": 250.0},
    ])
    conn = connector.connect(
        user=snowflake.user, account=snowflake.account, warehouse=snowflake.warehouse,
        role=snowflake.role, database=snowflake.database, schema=snowflake.schema,
        ocsp_fail_open=True, **snowflake.connector_params(),
    )
    try:
        cur = conn.cursor()
        try:
            # Create UNQUOTED so Snowflake folds to upper-case — the compiler
            # references the base table unquoted too, so both resolve to the same
            # upper-cased object.
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}orders "
                "(ORDER_ID NUMBER, REGION VARCHAR, PRODUCT_ID NUMBER, REVENUE_USD FLOAT)"
            )
            write_pandas(conn, rows, "ORDERS",
                         database=snowflake.database, schema=snowflake.schema)
            # Marker row (the promised marker model).
            managed = snowflake.full_table_name("semantic_smoke_marker")
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(conn, pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": "n/a"}]),
                         managed.split(".")[-1].strip('"'),
                         database=snowflake.database, schema=snowflake.schema)
        finally:
            cur.close()
    finally:
        conn.close()
```

The transform's param name (`snowflake`) MUST match the storage output port name;
it is injected as a typed `Snowflake` handle. **Never type it `Any`** — an
untyped param gets a raw `Context` with no driver methods.

### Step 4 — Wire `spec.py`: transform + storage port + `.semantic_tools()`

`.semantic_tools(service=...)` auto-wires the four MCP tools + an mcp-api port.
**Promise every annotated model** on the storage port so its attributes reach the
kernel-generated manifest (and thus the `.nxd/semantic/<model>.json` payloads).
Add the marker model so produce-verification passes.

```python
# spec.py
from nxd.spec import code, data_product, data_product_output, storage
from transform import transform
from models import orders, provision_marker   # provision_marker = the marker model

INFRA_PROFILE = "<infra-profile-name>"

_storage = (
    data_product_output()
    .promise(provision_marker)
    .promise(orders)
    .port("snowflake", storage(f"/infra-profile/{INFRA_PROFILE}#/services/<snowflake>"))
)

spec = (
    data_product(name="my-semantic-dp", domain="...", version="1.0.0-dev",
                 infra_profile=INFRA_PROFILE)
    # Seeds the base table(s) + the marker row. No semantic-view DDL.
    .transform(
        code(transform).compute(f"/infra-profile/{INFRA_PROFILE}#/services/<compute>")
    )
    .output(_storage)
    # ONE line — auto-wires list_models, semantic_model, describe_model,
    # run_semantic_query + the mcp-api port (default port_name="mcp-api",
    # mcp_path="/mcp"). Replaces the old build_semantic_tools + 4x rpc_function loop.
    .semantic_tools(service="<mcp-service-name>")
)
```

`semantic_tools(service, *, port_name="mcp-api", mcp_path="/mcp")` —
`service` is the infra-profile service name the MCP RPC port binds to.

Key facts:
- **Do NOT also call `data_product_rpc_output()`.** `.semantic_tools()` IS the RPC
  output; calling it when an RPC output already exists (or twice) raises
  `ValidationError("Data Product has RPC Output already configured")`.
- **Promise every annotated model**, or its attributes never reach the manifest
  and its `.nxd/semantic/<model>.json` payload is never written.
- **A `.transform(...)` is required** — it seeds the base tables the tools query
  AND bundles the sibling `models.py` (the `**/*.py` glob runs on the
  transform/compute path).
- **No `@on_provision`, no view DDL.** `run_semantic_query` compiles against the
  base tables directly. (The older provision-hook + `<MODEL>_SEMANTIC` view split
  is obsolete under `.semantic_tools()`.)
- **Plain `storage(...)`** — never `.config(...).as_view(...)` (the facade is
  mutually exclusive with `.transform()`).

Add to `requirements.txt`:

```
nxd.data_product[spec]
nxd.drivers[rpc]
snowflake-connector-python[pandas]
pandas
pyyaml>=6.0.2
```

`pyyaml` is needed by the `.semantic_tools()` manifest fallback
(`_manifest_compile`) — in the split-pod k8s/rpc topology the MCP server pod runs
no kernel, so the tools compile the same `__nxd_semantic__` blobs from the bundled
`models.yaml` instead of from `.nxd/semantic/*.json`. See
`reference/runtime-and-dependencies.md`.

---

### Step 5 — Glossary links and cross-DP lineage (optional)

`semantic_model(...).link(...)` attaches governed glossary terms (model-level and
per-attribute); `attribute(...).referencing(...)` declares a cross-DP foreign key
the discover UI renders as a SEMANTIC RELATIONSHIP.

```python
# models.py — glossary links + a cross-DP FK on a downstream fact.
from nxd.spec import Predicate, attribute

orders = (
    semantic_model("orders")
    .link(Predicate.GlossaryTerm, "/data-product/demo/glossary-dp#/terms/order")
    .link("REGION", Predicate.GlossaryTerm,
          "/data-product/demo/glossary-dp#/terms/region")
    .schema({
        # SUBJECT_ID is a cross-DP FK to an upstream spine.
        "SUBJECT_ID": _annotate(
            attribute(int64(), "SUBJECT_ID").referencing(
                data_product="pharma-subjects-demo", model="subjects",
                attribute=["SUBJECT_ID"]),
            {"kind": "dimension", "name": "subject_id",
             "description": "Subject FK.", "type": "number"},
        ),
        ...
    })
)
```

Declare the runtime dependency with `.input(...).source(...)` in `spec.py`
(before `.transform()`); the `.referencing(...)` makes the FK render as a semantic
relationship. Cross-DP joins resolve at QUERY time via the live mesh — the
downstream transform seeds only its own base tables. See
`reference/runtime-and-dependencies.md` for the full lineage form.

---

## Migrating an old-pattern DP

If a DP still uses `registry.py` + `tools.py` + `provision.py` +
`data_product_rpc_output()`:

1. **Move the vocabulary into `models.py`.** For each registry `.model()` /
   `.dimension()` / `.metric()` / `.join()`, write the equivalent
   `__nxd_semantic__` blob on the matching attribute (Step 2). Promise every model.
2. **Delete `registry.py` and `tools.py`.** The four tools are auto-generated.
3. **Delete `provision.py` and the view DDL.** Fold any base-table creation into
   the transform as `CREATE OR REPLACE TABLE` (Step 3). Drop the `.provision(...)`
   call and the `<MODEL>_SEMANTIC` view entirely.
4. **Replace the spec RPC block** (`build_semantic_tools` + the `rpc_function`
   loop + `rpc_server(...)` port) with one `.semantic_tools(service=...)` call.
5. **Add `pyyaml>=6.0.2`** to `requirements.txt`.
6. Keep `.startup_timeout(...)` off — it is not in the canonical pattern; add it
   back on `.transform(...)` only if cold-boot contention demands it (never on a
   provision call — there is no provision call anymore).

The 8 mesh DPs under `evals/query-loop/mesh/` are migrated reference examples.

---

## Invariants — NEVER violate these

- **Never re-implement the compiler or MCP tools.** They live in
  `nxd.experimental.semantic` (shipped with the `nxd.data_product` wheel) and are
  auto-wired by `.semantic_tools()`. Import; never copy.
- **One flag, not a hand-wired loop.** Use `.semantic_tools(service=...)`. Do NOT
  hand-write `build_semantic_tools` + `rpc_function` + `rpc_server` — and never
  call `data_product_rpc_output()` alongside it (raises `ValidationError`).
- **Promise every annotated model.** Un-promised model → no manifest attributes →
  no `.nxd/semantic/<model>.json` payload → that model is invisible to the tools.
- **The semantic vocabulary is per-field `__nxd_semantic__` blobs**, injected via
  the `_annotate()` stopgap until a public setter ships. Keep it isolated
  to `models.py`.
- **No `@on_provision`, no view DDL.** The tools compile against base tables. Seed
  them with `CREATE OR REPLACE TABLE` + `write_pandas` in the transform.
- **Always declare a `.transform(...)`** — it seeds the base tables AND bundles
  `models.py`.
- **Chasm-trap**: do not put metrics from two different models in one
  `run_semantic_query` call — the compiler raises `CompileError`. Surface it.
- **Agg enum is closed**: count, count_distinct, sum, avg, min, max.
- **Read-only, 200-row cap**: the query path is aggregated and capped. No raw-SQL
  passthrough.
- **All modules flat at the DP root**: never a `transform/` subdir; import flat.
- **`pyyaml>=6.0.2` in requirements** for the split-pod manifest fallback.
- **Matched wheel version set**: `core` + `drivers` + `data_product` all the same
  version (and recent enough to carry `.semantic_tools()` / the kernel's semantic emitter).
  A stale `core` fails at runtime with
  `Error deserializing context: missing field secret_password`. See
  `reference/runtime-and-dependencies.md`.

---

## Reference docs

| File | Content |
|------|---------|
| `reference/overview.md` | Design + how `__nxd_semantic__` annotations flow to the 4 tools |
| `reference/registry-authoring.md` | Full role grammar + auto-derivation + worked example |
| `reference/compiler-and-routing.md` | Compile paths + chasm-trap + Snowflake dialect |
| `reference/runtime-and-dependencies.md` | Requirements, wheel version, payload delivery + fallback, lineage |
| `reference/scripts/templates/semantic_dp.py.tmpl` | Complete models.py + transform.py + spec.py example |
| `reference/scripts/scaffold_semantic_dp.py` | Scaffold automation (writes models/transform stubs + requirements, prints spec wiring) |

---

## Consuming the deployed DP

This skill is the **producer** side — it builds the semantic-layer DP and its
four MCP tools. To **query** a deployed one (natural-language question → concept
selection → governed SQL), use the **nxd-data-product-query** skill: its
"Semantic-layer MCP ports" section drives the
`list_models` / `describe_model` / `run_semantic_query` discover→select→run
protocol and the grain-safety (chasm-trap) recovery against a live mesh.
