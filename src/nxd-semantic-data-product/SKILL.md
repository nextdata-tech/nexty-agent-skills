---
name: nxd-semantic-data-product
description: Builds a governed text-to-SQL / metrics / semantic-layer data product on Nextdata OS, exposing curated metrics and dimensions over MCP so an AI agent can answer natural-language questions without writing raw SQL. Use when the task is to create or extend a data product that lets agents query business metrics by name (e.g. order_count, revenue) sliced by dimensions (e.g. region, product_category), when you need NL-to-SQL governance over a Snowflake data product, or when exposing a semantic layer as an MCP server tool set. The skill generates only the per-DP registry; the shared compiler and MCP tool factory are vendored — never re-authored.
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
MCP tool factory are vendored shared code (`semantic/` kit) that you copy
verbatim into every DP. The scaffold script automates the copy.

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
from semantic.registry import Agg, Cardinality, SemanticRegistry

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

### Step 3 — Copy the vendored semantic/ kit

Copy `reference/scripts/semantic/` verbatim into `<dp-dir>/transform/semantic/`.
Use the scaffold script to do this automatically (step 4). Never edit the kit
files inside the DP — all fixes go to the canonical source in
`reference/scripts/semantic/` first.

### Step 4 — Run the scaffold script

```bash
uv run python reference/scripts/scaffold_semantic_dp.py <dp-dir>
```

The scaffold copies `semantic/` into `<dp-dir>/transform/semantic/`, writes a
placeholder `registry.py`, and prints the spec.py wiring block and the
requirements lines you need.

### Step 5 — Wire `spec.py` with `data_product_rpc_output()`

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
from semantic import build_semantic_tools
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

See `reference/runtime-and-dependencies.md` for version-skew notes.

---

## Invariants — NEVER violate these

- **Never re-author the compiler or MCP tools.** `semantic/compiler.py`,
  `semantic/dialect.py`, and `semantic/mcp_tools.py` are shared infrastructure.
  Copy them verbatim. Report bugs to the kit maintainers.
- **Chasm-trap**: do not put metrics from two different models in one
  `run_semantic_query` call. The compiler raises `CompileError` with an
  actionable message; surface it to the user.
- **Agg enum is closed**: COUNT, COUNT_DISTINCT, SUM, AVG, MIN, MAX. No custom
  aggregation functions.
- **Read-only, 200-row cap**: the query path is aggregated and capped. Raw SQL
  passthrough is not a feature of this kit.
- **extra_dimensions is an override only**: rely on the auto-derivation from
  N:1 joins. Only set `extra_dimensions` when the auto-derived set is wrong.

---

## Reference docs

| File | Content |
|------|---------|
| `reference/overview.md` | Two-layer design + what the kit provides |
| `reference/registry-authoring.md` | Full fluent API + worked generic example |
| `reference/compiler-and-routing.md` | Three compile paths + chasm-trap |
| `reference/runtime-and-dependencies.md` | Requirements, version-skew notes |
| `reference/adr-020-convergence.md` | ADR-020 migration table |
| `reference/scripts/semantic/` | Vendored kit — copy verbatim into each DP |
| `reference/scripts/scaffold_semantic_dp.py` | Scaffold automation |
