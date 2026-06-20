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

### Step 2 — Author `registry.py` (flat at the DP root)

Create `<dp-dir>/registry.py` using the fluent `SemanticRegistry`
builder. See `reference/registry-authoring.md` for the full API and a worked
generic example.

**Keep every module flat at the DP root** — `registry.py`, `tools.py`,
`transform.py`, `models.py`, `spec.py` are all siblings. Do NOT create a
`transform/` subdir package. A subdir package forces package-qualified imports
(`from transform.registry import REGISTRY`) which need the DP root on
`sys.path` — absent in the rpc subprocess, where only the extracted script's
own directory is on the path. Flat siblings let the extracted tool scripts
resolve `from registry import REGISTRY` against the script directory.

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

### Step 3 — Author `tools.py` with MODULE-LEVEL tool functions

`code(fn)` extracts a function's source via `inspect.getsource` over
**module-level** AST nodes. `build_semantic_tools(REGISTRY)` returns **closures**
(`build_semantic_tools.<locals>.list_models`) — `code()` cannot locate a closure,
so the pod never builds. You must author your own top-level
`list_models` / `describe_model` / `run_semantic_query` in a flat `tools.py`
that delegate to the library compiler.

Create `<dp-dir>/tools.py` with three module-level functions. Each is decorated
`@function(...)` + `@mcp.tool(...)`, imports `REGISTRY` flat
(`from registry import REGISTRY`), and delegates to the library
(`compile_selection` / `semantic_view_query` / `SnowflakeDialect`). Copy the
exact pattern from the reference `tools.py` referenced in
`reference/scripts/templates/transform_provision.py.tmpl` — no query logic is
duplicated; every function re-derives the dialect and compiled SQL from the
library.

```python
from nxd.drivers.rpc import Request, Response, function, mcp
from registry import REGISTRY
from nxd.experimental.semantic.compiler import (
    CompileError, compile_selection, semantic_view_query,
)
from nxd.experimental.semantic.dialect import SnowflakeDialect

_DIALECT = SnowflakeDialect(view_name="")

@function(name="list_models")
@mcp.tool(name="list_models", description="...")
def list_models(request: Request) -> Response:
    ...  # iterate REGISTRY.models

@function(name="describe_model")
@mcp.tool(name="describe_model", description="...")
def describe_model(request: Request) -> Response:
    ...

@function(name="run_semantic_query")
@mcp.tool(name="run_semantic_query", description="...")
def run_semantic_query(snowflake, request: Request) -> Response:
    ...  # compile_selection / semantic_view_query against the live view
```

### Step 4 — Author `transform.py` (MANDATORY) and wire `spec.py`

**The transform is mandatory, not optional.** The rpc-output `code(fn)` path
ships **only** the extracted `__<fn>__.py` tool scripts into the image — NOT the
sibling modules they import (`registry.py`, `tools.py`). Those siblings are
bundled by the `**/*.py` glob that runs on the **transform/compute** output path.
Without a `.transform(...)`, the pod dies at startup with
`ModuleNotFoundError: No module named 'registry'`. So every semantic DP **must**
declare `.transform(code(transform).compute(...))`.

The transform provisions the semantic view the MCP tools query (via
`native_semantic_view_ddl` / `plain_view_ddl` from the library) AND triggers the
sibling bundling. Mirror the reference `transform.py` referenced in
`reference/scripts/templates/transform_provision.py.tmpl`.

NXD exposes MCP tools **only** through `spec.py` via `data_product_rpc_output()`.
There is NO module-level `tools` list discovery — a bare
`tools = build_semantic_tools(REGISTRY)` in any file exposes **zero** MCP tools.

Add the following block to your `spec.py` (see
`reference/scripts/templates/spec_rpc_output.py.tmpl` for full annotation and
`reference/scripts/templates/transform_provision.py.tmpl` for a complete example):

```python
from nxd.spec import (
    data_product,
    data_product_output,
    data_product_rpc_output,
    rpc_function,
    rpc_server,
    storage,
    code,
)
from nxd.experimental.semantic import build_semantic_tools
from registry import REGISTRY
from tools import list_models, describe_model, run_semantic_query
from transform import transform
from models import provision_marker

# build_semantic_tools(REGISTRY) is used ONLY for each tool's request/response
# schema descriptors and description — NOT for its callable. The callable is the
# module-level function from tools.py, which code() can locate.
_tool_map = {t.name: t for t in build_semantic_tools(REGISTRY)}

_rpc = data_product_rpc_output()
for _fn, _name in [
    (list_models, "list_models"),
    (describe_model, "describe_model"),
    (run_semantic_query, "run_semantic_query"),
]:
    _t = _tool_map[_name]
    _rpc = _rpc.function(
        rpc_function(code(_fn), _t.request_model, _t.response_model)
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
    # MANDATORY — provisions the semantic view AND makes the **/*.py glob bundle
    # registry.py / tools.py into the image so the extracted tool scripts import.
    .transform(code(transform).compute("<infra-profile-path>#/services/<compute>"))
    .output(
        data_product_output()
        .promise(provision_marker)
        .port("snowflake", storage("<infra-profile-path>#/services/<snowflake>"))
    )
    .output(_rpc)
)
```

Key facts:
- The tool callable passed to `code(_fn)` is the **module-level** function from
  `tools.py` — never `build_semantic_tools(...)[i].fn` (a closure `code()` can't
  extract).
- `build_semantic_tools(REGISTRY)` is reused ONLY for each tool's
  `.request_model` / `.response_model` / `.description`.
- `rpc_function(code(fn), request_model, response_model)` — all three positional
  arguments are required.
- `.transform(...)` is **mandatory** — it bundles the sibling modules.
- `.description(t.description)` — chainable; sets the MCP tool description.
- `.enable_endpoints()` — publishes the HTTP+MCP endpoint.
- `.mcp_path("/mcp")` — sets the MCP mount path on the rpc_server port.

**Base tables must exist before promise verification.** The kernel runs promise
verification **before** the transform on this output path, so a DP that seeds its
own base tables in the transform fails verification (tables don't exist yet).
Either:
- **Facade over pre-existing tables** (recommended for production): reference
  externally-loaded tables via `source_aligned_input(...)` and provision the view
  with `storage(...).config(SnowflakeConfig().as_view(sql_script(...)))`, which
  runs at provision time. See
  `examples/features/drivers/snowflake-storage/snowflake-source-aligned-facade/`
  in the nxd repo.
- **Self-seed** (self-contained demo): the transform seeds the base tables — but
  a pure post-verify transform-seed will NOT pass verification in one launch.
  See `reference/runtime-and-dependencies.md`.

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
- **Never pass `code(t.fn)` over `build_semantic_tools(...)`**: those are closures
  `code()` cannot extract. Author module-level `tools.py` functions and pass
  `code(<module_fn>)`; reuse `build_semantic_tools(...)` only for the schemas.
- **Always declare a `.transform(...)`**: it is what bundles the sibling
  `registry.py` / `tools.py` modules into the image. `.output(_rpc)` alone ships
  only the extracted tool scripts → `ModuleNotFoundError` at pod startup.
- **All modules flat at the DP root**: never a `transform/` subdir package.
  Import flat (`from registry import REGISTRY`).
- **Matched wheel version set**: `core` + `drivers` + `data_product` must all be
  the same version (and `nxd_data_product >= 0.41.90`). A stale `core` against a
  newer `data_product` fails at runtime with
  `Error deserializing context: missing field secret_password`. See
  `reference/runtime-and-dependencies.md`.

---

## Reference docs

| File | Content |
|------|---------|
| `reference/overview.md` | Two-layer design + what the library provides |
| `reference/registry-authoring.md` | Full fluent API + worked generic example |
| `reference/compiler-and-routing.md` | Three compile paths + chasm-trap |
| `reference/runtime-and-dependencies.md` | Requirements, wheel version, pip registry notes |
| `reference/scripts/templates/transform_provision.py.tmpl` | Complete spec.py + tools.py + transform.py wiring (flat layout, module-level tools, mandatory transform) |
| `reference/scripts/scaffold_semantic_dp.py` | Scaffold automation (writes flat registry/tools/transform/models/spec stubs, prints requirements) |

---

## Consuming the deployed DP

This skill is the **producer** side — it builds the semantic-layer DP and its
three MCP tools. To **query** a deployed one (natural-language question → concept
selection → governed SQL), use the **nxd-data-product-query** skill: its §6d
"Semantic-layer MCP ports" drives the `list_models` / `describe_model` /
`run_semantic_query` discover→select→run protocol and the grain-safety (chasm-trap)
recovery against a live mesh.
