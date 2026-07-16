---
name: nxd-semantic-data-product
description: Builds a governed text-to-SQL / metrics / semantic-layer data product on Nextdata OS, exposing curated metrics and dimensions over MCP so an AI agent can answer natural-language questions without writing raw SQL. Use when the task is to create or extend a data product that lets agents query business metrics by name (e.g. order_count, revenue) sliced by dimensions (e.g. region, product_category), when you need NL-to-SQL governance over a Snowflake data product, or when exposing a semantic layer as an MCP server tool set. Also covers INFERRING the semantic model when no schema doc exists — profiling a materialized source table (local DuckDB sample) and deriving grains, metrics, dimensions, joins, and PII flags from the profile plus the user's natural-language questions. The author writes only per-field semantic annotations on the models; the one-line .semantic_tools() spec flag auto-generates the four governed MCP tools from the installed nxd.data_product wheel.
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

# nxd-semantic-data-product skill

## Overview

A semantic-layer data product exposes **named metrics and dimensions** over MCP.
An AI agent calls `run_semantic_query` with concept names; the data product
compiles a correct, governed SQL query and returns rows — no raw SQL escapes the
DP boundary.

**You author only the per-field semantic annotations on the models.** A single
`.semantic_tools(service=...)` flag on the spec auto-generates the four governed
MCP tools at pod boot. The kernel compiles the annotations into typed payloads; the
compiler, dialect, and tool factory ship in the `nxd.data_product` wheel as
`nxd.experimental.semantic` — imported, not vendored. The four tools:

| Tool | Purpose |
|------|---------|
| `list_models` | Enumerate the semantic models (entities) with grain + metric/dimension counts |
| `semantic_model` | Return one model's full registry projection (raw metrics/dimensions/joins) |
| `describe_model` | Human-oriented detail for one model: metrics (+ compatible dimensions), dimensions (+ PII flags), joins |
| `run_semantic_query` | Compile a concept selection to governed SQL, run it, return rows |

See `reference/overview.md` for the design and how annotations flow to the tools.

> **This skill teaches the `.semantic_tools()` pattern.**

> **Two flows use the inference in this skill — pick the right one before continuing.**
> - **Regular platform flow (this skill):** a governed semantic DP on the Nextdata OS
>   platform — Snowflake/warehouse output, the split-pod k8s `.semantic_tools()`
>   topology, and a deploy step. The workflow, credential, deploy, and "consuming a
>   deployed DP" sections below assume this flow.
> - **Local end-to-end flow:** the AI generates **and runs** the whole data product
>   locally on the desktop supervisor. That DP has a **different shape** — a local
>   DuckDB output port, dlt-in-transform ingestion, and a local Python executor — and
>   that shape is owned by the **nxd-generate-dp** skill. Use this skill only for the
>   shape-neutral part it shares (profiling a source, inferring the model, writing the
>   `__nxd_semantic__` annotations), then hand off to nxd-generate-dp. **Do NOT follow
>   the Snowflake / credential / deploy / consume steps below in the local flow** —
>   they are platform-only and produce the wrong DP shape locally.

---

## Workflow

### Step 1 — Derive the semantic vocabulary from the schema

Interview the user or read the table DDL to establish, per source table:

1. **Model** — the physical table: a unique name + the **grain** column (the
   entity key, e.g. `order_id`) + an optional description.
2. **Dimensions** — columns an agent can group or filter by. Each: a concept
   `name`, the physical `column`, a logical `type` (`string` / `date` / `number`),
   a `description`, and `pii: true` if governed.
3. **Metrics** — named aggregated measures. Each: a concept `name`, the physical
   `column` it aggregates, the `agg` function (`count`, `count_distinct`, `sum`,
   `avg`, `min`, `max`), a `description`, and `boolean: true` for a flag that counts
   truthy rows.
4. **Joins** — documented N:1 relationships, declared on the MANY-side model's join
   key: `to_model` (the ONE side), `to_column`, `cardinality: many_to_one`.
   Cross-model dimension reach is **auto-derived** from N:1 joins by the compiler.

### Step 1-alt — Infer from a profiled source + the user's questions

When there is **no schema doc** — only a materialized sample of the source and the
user's natural-language questions — derive the Step-1 vocabulary yourself. Steps
2–4 (models.py / transform.py / spec.py) are then **unchanged**.

**1. Profile the materialized tables → `schema.json`.** A sample load (e.g. dlt)
lands each source table as `main.<name>` in a local DuckDB file. Introspect ALL of
them in one pass with the nxd-mesh-analyzer skill's profiler (DuckDB mode — needs
the `duckdb` package, e.g. `uv run --with duckdb`) and **save the combined document
as `schema.json`**:

```bash
python <nxd-mesh-analyzer>/scripts/profile_tabular.py sample.duckdb <table1> <table2> ... > schema.json
```

With two or more tables the profiler emits ONE combined document —
`{"path": ..., "format": "duckdb", "tables": {<table>: <profile>, ...}}` — where
each table's profile carries, per column: `declared_type`, `nullable`, `null_pct`,
`distinct_count`, `cardinality` (distinct/total, exact full-table), `sample_values`,
plus freshness hints. `schema.json` is the **handoff artifact**: keep it in the
workspace, infer by READING it (re-query the DuckDB file only for targeted
follow-ups like the join-containment probe below), and leave it as the evidence
for how the model was derived. **Ground the model in this profile — annotate only
columns that exist in it; never invent or rename columns.**

**2. Classify each column from its profile signals:**

| Profile signal | Likely role |
|---|---|
| `cardinality` == 1.0 AND `null_pct` == 0 (exact full-table), id-ish name (`*_id`, `*_key`, uuid samples) | **grain** candidate (the model's entity key) |
| id-ish name, cardinality < 1.0, values match another table's grain | **join** key candidate (MANY side → `to_model`, `many_to_one`) — validate before declaring (see below) |
| numeric (`DOUBLE`/`DECIMAL`/amount-ish name), not an id, **additive** (see below) | **metric** candidate |
| `BOOLEAN` / true-false samples | boolean-flag **metric** (`"boolean": true` — MUST pair with `"agg": "sum"`) and/or dimension |
| low-cardinality string (`segment`, `status`, `channel`, country codes) | **dimension** (`type: "string"`) |
| `DATE`/`TIMESTAMP` (freshness hints) | **dimension** (`type: "date"`) |
| samples look like emails, names, phones, addresses | dimension with **`"pii": true`** — flag from the DATA, even if no question asks for it (NULLs in some rows don't unmark it) |

**Grain selection.** Trust only the exact full-table `cardinality` (DuckDB mode
computes it over the whole table; a sample-only profile can fake uniqueness). If
SEVERAL columns are fully unique, prefer the one whose name matches the table's
entity (`orders` → `order_id`) and/or the one other tables' FK candidates point
at. If NO single column is unique, use a **composite grain** — a `{"kind":
"grain"}` blob on each component column; confirm the combination is unique with a
targeted `COUNT(*) vs COUNT(DISTINCT (a, b))` query.

**Join validation.** Never declare a join from name similarity or a handful of
overlapping `sample_values` alone. Before writing the blob, verify BOTH:

- **Containment** — every non-null FK value resolves on the ONE side:
  `SELECT COUNT(*) FROM <many> WHERE <fk> IS NOT NULL AND <fk> NOT IN
  (SELECT <to_column> FROM <one>)` must be 0 (or explain the orphans).
- **Uniqueness of the ONE side** — `to_column` must be the target model's grain
  (full-table cardinality 1.0), or `many_to_one` is a lie.

Declare the blob on the MANY-side FK with explicit `to_model` and `to_column`. If
the samples don't overlap, that is evidence AGAINST the join — probe or ask.

**Additive vs non-additive numerics.** A numeric column is a `sum` metric only if
it is **additive across rows** (amounts, quantities, per-row durations). Balances,
scores, points, percentages, rates, and point-in-time snapshots (e.g.
`loyalty_points`, `account_balance`, `discount_pct`) are NOT sum metrics — summing
them answers nothing. Aggregate such a column only when a question justifies it
(`avg`/`min`/`max` can be legitimate); otherwise leave it unannotated or expose it
as a `number` dimension.

**DuckDB declared type → `AttributeSpec` data type** (for the `models.py`
attributes):

| DuckDB `declared_type` | `nxd.spec.data_types` |
|---|---|
| `VARCHAR` / `TEXT` | `string()` |
| `TINYINT`/`SMALLINT`/`INTEGER`/`BIGINT`/`HUGEINT` | `int64()` |
| `DOUBLE` / `FLOAT` / `REAL` | `float64()` |
| `DECIMAL(p,s)` / `NUMERIC` | `decimal(p, s)` (or `float64()` if precision is not load-bearing) |
| `BOOLEAN` | `boolean()` |
| `DATE` | `date32()` |
| `TIMESTAMP` / `TIMESTAMPTZ` | `timestamp()` |

**3. Let the QUESTIONS drive what you declare** — the profile says what a
column *could* be; the questions say what it *must* be:

- "total/revenue/spend ..." → a `sum` metric on the money column.
- "how many X ..." over a flag ("churned", "first-time") → a metric on the
  boolean column with **`"agg": "sum"` AND `"boolean": true`** — the dialect
  defines the boolean CASE-sum ONLY for `sum` (`SUM(CASE WHEN ... THEN 1 ELSE
  0 END)`); `"boolean": true` with any other agg is invalid. Never a plain
  numeric SUM of a flag.
- "average ..." → `avg`. "how many distinct/top N by count" → `count` /
  `count_distinct` on the grain/key. A column serving two aggs gets a
  `{"roles": [...]}` wrapper. "by/per <attribute>" → that column is a dimension.
- A question slicing one table's metric by another table's attribute (e.g. orders
  by customer country) → declare the validated N:1 **join** on the MANY-side FK;
  the compiler auto-derives the cross-model dimension reach.
- "per order / per customer ..." confirms the **grain** of each model (one row per
  entity — cross-check against exact full-table cardinality 1.0).

Declare what the questions need plus the obviously useful dimensions; don't
exhaustively annotate every column, and don't declare metrics no question motivates
(that is how non-additive numerics end up as nonsense `sum`s).

**3b. Surface ambiguity — don't silently resolve it.** The role grammar has
**no filtered metrics, no derived ratios, and no default filters**: a metric is
exactly `<agg>(<column>)`. When a question's business definition is ambiguous
against the profiled data, do NOT hard-code one interpretation silently:

- *Status-qualified totals* — "total revenue" over a table whose `status` samples
  include `refunded` / `cancelled`: the metric can only be the unconditional
  `sum`. Say so in the metric `description` (e.g. "Gross order amount across ALL
  statuses, including refunded and cancelled") AND declare the status column as a
  dimension so consumers filter at query time.
- *Derived ratios* ("revenue per customer", "churn rate") — not expressible as one
  metric; expose the component metrics and state that the ratio is computed by the
  caller from two queries.
- In an interactive session, ask (AskUserQuestion) instead of guessing; in a
  non-interactive run, record the ambiguity and your chosen interpretation in the
  metric descriptions and your final report.

**4. Naming invariant.** Each `semantic_model(name)` argument is the **bare
unquoted lowercase physical table name** — `semantic_model("customers")` for the
table profiled as `main.customers` (never `"main.customers"`, never a prettified
rename). Attribute names must match the profiled column names **byte-exactly**
(post-dlt snake_case preserved — `customer_id`, not `CUSTOMER_ID`). The transform
seeds those same tables (unquoted), so compiler, seed, and profile resolve to one
object.

### Step 2 — Author `models.py` with per-field `__nxd_semantic__` annotations

The semantic vocabulary is declared as a reserved `__nxd_semantic__` JSON blob on
each model attribute. The kernel reads those blobs from every **promised** model's
manifest, compiles them into a typed `SemanticRegistry`, and delivers it to the pod
at boot as `<root>/.nxd/semantic/<model>.json`; the runtime rebuilds the four tools
from those payloads.

> **STOPGAP — no public author API yet.** `AttributeSpec` has no public
> `.semantic_annotation()` setter, so the blob is injected by writing the
> **private** `_metadata` dict directly via an `_annotate()` helper — the only
> mechanism until that public API ships. Keep the injection isolated to
> `models.py` and clearly marked. Before publishing, verify the wheel: if a public
> `AttributeSpec.semantic_annotation(blob)` exists, use it instead of `_annotate()`.

Keep every module **flat at the DP root** — `models.py`, `transform.py`, `spec.py`
are siblings. No `transform/` subdir package.

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

# To put COUNT on the grain column, patch a full {"roles": [...]} list post-hoc
# (the bare {"kind": "grain"} shorthand has no inline multi-role form; the roles
# list REPLACES the bare-grain blob):
_annotate(orders._attributes["ORDER_ID"], {"roles": [
    {"kind": "grain"},
    {"kind": "metric", "name": "order_count", "agg": "count_distinct",
     "description": "Distinct orders placed."},
]})
```

**Role grammar** (one blob per column):

| Role | Blob |
|------|------|
| grain | `{"kind": "grain"}` |
| dimension | `{"kind": "dimension", "name": ..., "description": ..., "type": ..., "pii": <bool?>}` |
| metric | `{"kind": "metric", "name": ..., "agg": "count\|count_distinct\|sum\|avg\|min\|max", "description": ..., "boolean": <bool?>}` |
| join | `{"kind": "join", "to_model": ..., "to_column": ..., "cardinality": "many_to_one"}` |
| multi-role | `{"roles": [ {...}, {...} ]}` |

See `reference/registry-authoring.md` for the full role vocabulary,
auto-derivation rules, and a worked example.

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
        # Create UNQUOTED so Snowflake folds to upper-case — the compiler
        # references the base table unquoted too, so both resolve to one object.
        conn.cursor().execute(
            f"CREATE OR REPLACE TABLE {fqn}orders "
            "(ORDER_ID NUMBER, REGION VARCHAR, PRODUCT_ID NUMBER, REVENUE_USD FLOAT)"
        )
        write_pandas(conn, rows, "ORDERS",
                     database=snowflake.database, schema=snowflake.schema)
        # Marker row (the promised marker model).
        managed = snowflake.full_table_name("semantic_smoke_marker")
        conn.cursor().execute(f"TRUNCATE TABLE IF EXISTS {managed}")
        write_pandas(conn, pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": "n/a"}]),
                     managed.split(".")[-1].strip('"'),
                     database=snowflake.database, schema=snowflake.schema)
    finally:
        conn.close()
```

The transform's param name (`snowflake`) MUST match the storage output port name;
it is injected as a typed `Snowflake` handle. **Never type it `Any`** — an untyped
param gets a raw `Context` with no driver methods.

### Step 4 — Wire `spec.py`: transform + storage port + `.semantic_tools()`

`.semantic_tools(service=...)` auto-wires the four MCP tools + an mcp-api port.
**Promise every annotated model** on the storage port so its attributes reach the
kernel-generated manifest (and thus the `.nxd/semantic/<model>.json` payloads); add
the marker model so produce-verification passes.

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
    # ONE line — auto-wires the four tools + the mcp-api port (defaults
    # port_name="mcp-api", mcp_path="/mcp").
    .semantic_tools(service="<mcp-service-name>")
)
```

`semantic_tools(service, *, port_name="mcp-api", mcp_path="/mcp")` —
`service` is the infra-profile service name the MCP RPC port binds to.

Key facts:
- **Do NOT also call `data_product_rpc_output()`.** `.semantic_tools()` IS the RPC
  output; adding another (or calling it twice) raises
  `ValidationError("Data Product has RPC Output already configured")`.
- **Promise every annotated model**, or its attributes never reach the manifest and
  its `.nxd/semantic/<model>.json` payload is never written.
- **A `.transform(...)` is required** — it seeds the base tables the tools query AND
  bundles the sibling `models.py` (the `**/*.py` glob runs on the compute path).
- **No `@on_provision`, no view DDL** — `run_semantic_query` compiles against the
  base tables directly.
- **Plain `storage(...)`** — never `.config(...).as_view(...)` (the facade is
  mutually exclusive with `.transform()`).

---

### Step 5 — Emit `requirements.txt` (REQUIRED deliverable)

The data product is not complete without its dependency file. **Write a
`requirements.txt`** (alongside `spec.py` / `models.py` / `transform.py`) listing
exactly:

```
nxd.data_product[spec]
nxd.drivers[rpc]
snowflake-connector-python[pandas]
pandas
pyyaml>=6.0.2
```

Do not skip this file — a DP that authors the model, spec, and transform but
never writes `requirements.txt` is unshippable (the compute pod can't install its
runtime). All five entries are load-bearing: `nxd.data_product[spec]` +
`nxd.drivers[rpc]` are the wheel + RPC driver the tools run on;
`snowflake-connector-python[pandas]` + `pandas` are the storage runtime; and
`pyyaml>=6.0.2` powers the `.semantic_tools()` manifest fallback
(`_manifest_compile`) — in the split-pod k8s/rpc topology the MCP server pod runs
no kernel, so the tools compile the same `__nxd_semantic__` blobs from the bundled
`models.yaml` instead of `.nxd/semantic/*.json`. See
`reference/runtime-and-dependencies.md`.

---

### Step 6 — Glossary links and cross-DP lineage (optional)

`semantic_model(...).link(Predicate.GlossaryTerm, "<term-uri>")` attaches
governed glossary terms (model-level and, with an attribute name as the first
arg, per-attribute). `attribute(int64(), "SUBJECT_ID").referencing(data_product=...,
model=..., attribute=[...])` on a schema attribute (still wrapped in `_annotate`
with its dimension blob) declares a cross-DP foreign key the discover UI renders
as a SEMANTIC RELATIONSHIP.

Declare the runtime dependency with `.input(...).source(...)` in `spec.py`
(before `.transform()`); the `.referencing(...)` makes the FK render as a semantic
relationship. Cross-DP joins resolve at QUERY time via the live mesh — the
downstream transform seeds only its own base tables. See
`reference/runtime-and-dependencies.md` for the full lineage form.

---

## Invariants — NEVER violate these

- **Never re-implement the compiler or MCP tools.** They live in
  `nxd.experimental.semantic` (shipped with the `nxd.data_product` wheel) and are
  auto-wired by `.semantic_tools()`. Import; never copy.
- **Use `.semantic_tools(service=...)`.** It IS the RPC output — never
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
  version, recent enough to carry `.semantic_tools()` / the kernel's semantic
  emitter. A stale `core` fails at runtime with `Error deserializing context:
  missing field secret_password`. See `reference/runtime-and-dependencies.md`.

## Reference docs

| File | Content |
|------|---------|
| `reference/overview.md` | Design + how `__nxd_semantic__` annotations flow to the 4 tools |
| `reference/registry-authoring.md` | Full role grammar + auto-derivation + worked example |
| `reference/compiler-and-routing.md` | Compile paths + chasm-trap + Snowflake dialect |
| `reference/runtime-and-dependencies.md` | Requirements, wheel version, payload delivery + fallback, lineage |
| `reference/scripts/templates/semantic_dp.py.tmpl` | Complete models.py + transform.py + spec.py example |
| `reference/scripts/scaffold_semantic_dp.py` | Scaffold automation (writes models/transform stubs + requirements, prints spec wiring) |

## Consuming the deployed DP

This skill is the **producer** side — it builds the semantic-layer DP and its four
MCP tools. To **query** a deployed one (natural-language question → concept
selection → governed SQL), use the **nxd-data-product-query** skill: its
"Semantic-layer MCP ports" section drives the `list_models` / `describe_model` /
`run_semantic_query` discover→select→run protocol and the grain-safety
(chasm-trap) recovery against a live mesh.
