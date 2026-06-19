---
name: nxd-semantic-data-product
description: Builds a governed text-to-SQL / metrics / semantic-layer data product on Nextdata OS, exposing curated metrics and dimensions over MCP so an AI agent can answer natural-language questions without writing raw SQL. Use when the task is to create or extend a data product that lets agents query business metrics by name (e.g. order_count, revenue) sliced by dimensions (e.g. region, product_category), when you need NL-to-SQL governance over a Snowflake data product, or when exposing a semantic layer as an MCP server tool set. The skill generates only the per-DP registry; the shared compiler and MCP tool factory are provided by the installed nxd.data_product wheel (nxd.experimental.semantic) — imported, not vendored.
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
  version: 0.1.0
---

# nxd-semantic-data-product skill

## Overview

A semantic-layer data product exposes **named metrics and dimensions** over MCP.
An AI agent calls `run_semantic_query` with concept names; the data product
compiles a correct, governed SQL query and returns rows — no raw SQL escapes the
DP boundary.

**The registry is the only artifact you author.** The compiler, SQL dialect, and
MCP tool factory are provided by the installed `nxd.data_product` wheel as the
`nxd.experimental.semantic` module — imported, not vendored. Every DP that
depends on `nxd.data_product[spec]` already has the module available.

See `reference/overview.md` for the two-layer design.

---

## Workflow

### Step 1 — Derive the semantic model from the schema

Interview the user or read the table DDL to establish:

1. **Models** — the physical tables. For each: a unique name, the grain column
   (the entity key; e.g. `order_id`), and an optional description.
2. **Dimensions** — columns an agent can group or filter by. For each: a unique
   concept name, which model owns it, the physical column name, a logical type
   (`string`, `date`, `number`), a human description, and a `pii` flag.
3. **Metrics** — named aggregated measures. For each: a unique concept name,
   which model it lives on, the `Agg` function
   (`COUNT`, `COUNT_DISTINCT`, `SUM`, `AVG`, `MIN`, `MAX`), the physical column
   (`*` for bare `COUNT`), a description, and `boolean=True` if the column is a
   flag that counts truthy rows.
4. **Joins** — documented N:1 relationships between models. For each: left model
   (MANY side), right model (ONE side), join-key pairs, and
   `cardinality=Cardinality.MANY_TO_ONE`. Cross-model dimension reach is
   **auto-derived** from N:1 joins — do not add `extra_dimensions` unless you
   need to override the derivation for a specific metric.

### Step 2 — Author only `registry.py`

Create `<dp-dir>/transform/registry.py` using the fluent `SemanticRegistry`
builder. See `reference/registry-authoring.md` for the full API and a worked
generic example.

```python
from nxd.experimental.semantic import Agg, Cardinality, SemanticRegistry

REGISTRY = (
    SemanticRegistry()
    .model("orders", grain="order_id", description="One row per order.")
    .model("products", grain="product_id")
    .dimension("region", model="orders", column="REGION", description="Sales region.")
    .dimension("category", model="products", column="CATEGORY",
               description="Product category.")
    .metric("order_count", model="orders", agg=Agg.COUNT_DISTINCT, column="order_id",
            description="Distinct orders placed.")
    .metric("revenue", model="orders", agg=Agg.SUM, column="REVENUE_USD",
            description="Total revenue in USD.")
    .join(left="orders", right="products",
          on=(("product_id", "product_id"),),
          cardinality=Cardinality.MANY_TO_ONE)
    .build()
)
```

`build()` validates referential integrity, checks for duplicate names, and
auto-derives which dimensions each metric can be sliced by from the N:1 joins.

### Step 3 — Run the scaffold script

```bash
uv run python reference/scripts/scaffold_semantic_dp.py <dp-dir>
```

The scaffold creates `<dp-dir>/transform/`, writes a placeholder `registry.py`
(with the correct `nxd.experimental.semantic` import), and prints the spec.py
wiring block and the requirements lines you need.

### Step 4 — Wire `spec.py` with `data_product_rpc_output()`

NXD exposes MCP tools **only** through `spec.py` via `data_product_rpc_output()`.
There is NO module-level `tools` list discovery — a bare
`tools = build_semantic_tools(REGISTRY)` in any file exposes **zero** MCP tools.

Add the following block to your `spec.py` (see
`reference/scripts/templates/spec_rpc_output.py.tmpl` for full annotation and
`reference/scripts/templates/transform_provision.py.tmpl` for a complete example):

```python
from nxd.spec import (
    data_product_rpc_output,
    rpc_function,
    rpc_server,
    code,
)
from nxd.experimental.semantic import build_semantic_tools
from registry import REGISTRY

_rpc = data_product_rpc_output()
for _t in build_semantic_tools(REGISTRY):
    _rpc = _rpc.function(
        rpc_function(code(_t.fn), _t.request_model, _t.response_model)
        .description(_t.description)
    )
_rpc = _rpc.port(
    "mcp-api",
    rpc_server("<infra-profile-path>#/services/<mcp-service-name>")
    .enable_endpoints()
    .mcp_path("/mcp"),
)

spec = (
    data_product(name="my-semantic-dp", ...)
    .output(_rpc)
    # Add inputs, transforms, additional outputs as needed.
)
```

Key facts:
- `rpc_function(code(t.fn), t.request_model, t.response_model)` — all three
  positional arguments are required.
- `.description(t.description)` — chainable; sets the MCP tool description.
- `.enable_endpoints()` — publishes the HTTP+MCP endpoint.
- `.mcp_path("/mcp")` — sets the MCP mount path on the rpc_server port.
- `build_semantic_tools(REGISTRY)` returns `list[SemanticTool]`; each carries
  `.fn`, `.request_model`, `.response_model`, `.description`.

Add to `requirements.txt`:

```
nxd.data_product[spec]
nxd.drivers[rpc]
snowflake-connector-python[pandas]
pandas
```

See `reference/runtime-and-dependencies.md` for version and registry notes.

---

## Invariants — NEVER violate these

- **Never re-implement the compiler or MCP tools.** The compiler, dialect, and
  MCP tool factory live in `nxd.experimental.semantic` (shipped with the
  `nxd.data_product` wheel). Import them; do not copy or re-author them. Report
  bugs to the `nxd.data_product` maintainers.
- **Chasm-trap**: do not put metrics from two different models in one
  `run_semantic_query` call. The compiler raises `CompileError` with an
  actionable message; surface it to the user.
- **Agg enum is closed**: COUNT, COUNT_DISTINCT, SUM, AVG, MIN, MAX. No custom
  aggregation functions.
- **Read-only, 200-row cap**: the query path is aggregated and capped. Raw SQL
  passthrough is not a feature of this library.
- **extra_dimensions is an override only**: rely on the auto-derivation from
  N:1 joins. Only set `extra_dimensions` when the auto-derived set is wrong.

---

## Reference docs

| File | Content |
|------|---------|
| `reference/overview.md` | Two-layer design + what the library provides |
| `reference/registry-authoring.md` | Full fluent API + worked generic example |
| `reference/compiler-and-routing.md` | Three compile paths + chasm-trap |
| `reference/runtime-and-dependencies.md` | Requirements, wheel version, pip registry notes |
| `reference/scripts/scaffold_semantic_dp.py` | Scaffold automation (writes registry stub, prints spec wiring) |

---

## Consuming the deployed DP

This skill is the **producer** side — it builds the semantic-layer DP and its
three MCP tools. To **query** a deployed one (natural-language question → concept
selection → governed SQL), use the **nxd-data-product-query** skill: its §6d
"Semantic-layer MCP ports" drives the `list_models` / `describe_model` /
`run_semantic_query` discover→select→run protocol and the grain-safety (chasm-trap)
recovery against a live mesh.
