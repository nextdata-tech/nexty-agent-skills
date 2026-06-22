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
  version: 0.3.0
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
# MODULE-LEVEL import of the typed Snowflake handle — REQUIRED (see two gotchas below).
from nxd.data_product.context import Snowflake
from registry import REGISTRY
from nxd.experimental.semantic.compiler import (
    CompileError, compile_selection, semantic_view_query,
)
from nxd.experimental.semantic.dialect import SnowflakeDialect

@function(name="list_models")
@mcp.tool(name="list_models", description="List the semantic models, their grain, and metric/dimension counts.")
def list_models(request: Request) -> Response:
    ...  # iterate REGISTRY.models

@function(name="describe_model")
@mcp.tool(name="describe_model", description="Describe one model's metrics, dimensions, joins, and PII flags.")
def describe_model(request: Request) -> Response:
    ...

@function(name="run_semantic_query")
@mcp.tool(name="run_semantic_query", description="Compile a concept selection to governed SQL and return rows.")
def run_semantic_query(snowflake: Snowflake, request: Request) -> Response:
    dialect = SnowflakeDialect(view_name="")   # built INSIDE the body, not at module level
    ...  # compile_selection / semantic_view_query against the live view
```

**Two extraction gotchas the rpc tool path WILL trip — both are deploy-breakers if ignored:**

1. **Type the storage-context param with its SPECIFIC driver handle (NOT untyped / `Any`), via a MODULE-LEVEL import.** The rpc runtime injects a non-`request` arg **by type**: a param typed with the driver context class (e.g. `Snowflake`, `Databricks`, `BigQuery` — whatever the DP's storage port provides) gets a real handle; an untyped / `Any` param gets a raw `Context` with no driver methods (`.connector_params()` etc.), and `run_semantic_query` fails live with `'Context' object has no attribute ...` / `Context cannot be converted to ContextData`. Import the concrete type at module level so `code()` extraction + `get_type_hints` resolve the annotation in the rpc subprocess — e.g. for a Snowflake-backed DP:
   ```python
   from nxd.data_product.context import Snowflake
   def run_semantic_query(snowflake: Snowflake, request: Request) -> Response: ...
   ```
   For a Databricks / BigQuery / other storage backend, import and annotate with that driver's context type instead.

2. **Never reference a module-level constant from inside an extracted tool** — inline it. `code()` extraction carries a tool's imports + the `def`/`class` it calls, but **drops module-level `=` assignments**. So `_DESC = "..."` + `@mcp.tool(description=_DESC)`, or a module-level `_DIALECT = SnowflakeDialect(...)` used in the body, raises `NameError` at rpc-server load → the tool fails to register → `tools/list` returns `[]` → `nxd mcp health` shows the DP `Broken`/`tool_count: 0`. Inline the description literal into each decorator and build per-call state (the dialect) **inside** the function body.

### Step 4 — Respect the lifecycle: provision seeds, transform produces, and wire `spec.py`

This is the single most error-prone part of a semantic DP. The rule is to use
each lifecycle function **for what it is for** — the deploy-breakers below all
come from mixing them up.

**(a) PROVISION the promised table + the semantic view — do NOT provision in the
transform.** The kernel runs output-port **promise verification BEFORE the
transform**. So one-time setup that the promise depends on — creating/seeding the
promised base table and creating the `<MODEL>_SEMANTIC` view — must happen in an
`@on_provision` function (runs before verification), wired via
`.provision(script("provision.py"))` (`UserCodeSpec` via `script(...)`; the
decorator is `@data_product.on_provision()` after `from nxd import data_product`
— the same form the `provision.py` example below + the reference templates use).
Putting that setup in the transform
fails verification — the table doesn't exist yet — with a status reason like
`Field MARKER_ID not found in the model`. **This is the load-bearing rule:
respect the lifecycle — provisioning is provision-time, not runtime.**

**(b) The transform is for RUNTIME data production — write real transform code
here if the DP has runtime work.** A `.transform(...)` is mandatory regardless,
because the rpc-output `code(fn)` path ships only the extracted `__<fn>__.py` tool
scripts — NOT the sibling modules they import (`registry.py`, `tools.py`); those
are bundled by the `**/*.py` glob that runs on the transform/compute output path,
so without a `.transform(...)` the pod dies `ModuleNotFoundError: No module named
'registry'`. If your DP computes derived tables, refreshes data on a schedule, or
otherwise produces data at runtime, do that work in the transform as normal.
What the transform must **never** do is (re)provision — seed/create the promised
table or the semantic view — because verification already ran; a transform that
duplicates provisioning's setup (or otherwise fails/times out) makes the DP flap
`Started`↔`Failed`.

For a DP whose data is **fully static seed** (like these demo DPs), there is no
runtime work, so its transform is legitimately a no-op — it exists only to
trigger sibling bundling:

```python
# transform.py — no runtime work for this static-seed DP; provisioning owns setup.
# (A DP with real runtime data production would write that logic here instead.)
def transform(context):
    print("semantic DP: data is static seed; setup owned by @on_provision")
```

**(c) `provision.py` must be SELF-CONTAINED.** The provision entrypoint runs
from its own `provision/` subdir, so a flat `from registry import ...` does NOT
resolve (`ModuleNotFoundError: registry`). Inline everything the seed needs — do
not import siblings; hardcode the `<MODEL>_SEMANTIC` view name rather than
importing the registry to compute it.

**(d) The view DDL must reference ONLY this DP's own tables.** Never call the
compiler's `native_semantic_view_ddl` / `plain_view_ddl` when the registry
declares a cross-DP join — those emit a JOIN to a table in ANOTHER DP's schema,
so `CREATE VIEW` binds a missing object and provision fails. Hand-author a
**single-table** `<MODEL>_SEMANTIC` view. Cross-DP joins resolve at QUERY time
via the live mesh, never at view-creation time.

**(e) Raise the provision timeout for heavy deps.** Provision must connect to
Snowflake + (cold) build `snowflake-connector-python[pandas]`+pandas. The
default kernel provision budget is 180s; a cold provision exceeds it →
`Timeout waiting for execution to start` → DP `Failed`. Set the factory kwarg
`data_product(..., provision_timeout_secs=600)` (NOT `.compute(provision_timeout_secs=...)`
— that signature doesn't exist on the installed wheel).

```python
# provision.py — SELF-CONTAINED. No sibling imports; view name hardcoded.
from nxd import data_product
from nxd.data_product.context import Snowflake

_VIEW_NAME = "SUBJECTS_SEMANTIC"   # = SnowflakeDialect.default_view_name(REGISTRY), hardcoded

@data_product.on_provision()
def provision(snowflake: Snowflake) -> None:   # the typed driver handle is injected, like the tools
    from snowflake import connector
    if snowflake is None or not snowflake.schema:
        return
    fqn = f"{snowflake.database}.{snowflake.schema}." if snowflake.database else f"{snowflake.schema}."
    conn = connector.connect(
        user=snowflake.user, account=snowflake.account, warehouse=snowflake.warehouse,
        role=snowflake.role, database=snowflake.database, schema=snowflake.schema,
        ocsp_fail_open=True, **snowflake.connector_params(),
    )
    try:
        cur = conn.cursor()
        # 1. write the promised marker model — MUST exist before verify (the storage
        #    port promises `subjects_marker` with schema {MARKER_ID, VIEW_NAME}).
        #    Skipping this is the exact `Field MARKER_ID not found` failure.
        cur.execute(f"CREATE OR REPLACE TABLE {fqn}SUBJECTS_MARKER (MARKER_ID NUMBER, VIEW_NAME VARCHAR)")
        cur.execute(f"INSERT INTO {fqn}SUBJECTS_MARKER VALUES (1, '{_VIEW_NAME}')")
        # 2. seed THIS DP's own base table(s)
        cur.execute(f"CREATE OR REPLACE TABLE {fqn}SUBJECTS (SUBJECT_ID NUMBER, SUBJECT_COUNTRY VARCHAR)")
        cur.execute(f"INSERT INTO {fqn}SUBJECTS VALUES (1,'US'),(2,'US'),(3,'DE'),(4,'FR')")
        # 3. create the SINGLE-TABLE semantic view (NO cross-DP JOIN; name hardcoded)
        cur.execute(f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS SELECT * FROM {fqn}SUBJECTS")
    finally:
        conn.close()
```

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
    script,
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
    # provision_timeout_secs is a FACTORY kwarg (not .compute(...)) — heavy
    # snowflake+pandas provision deps exceed the 180s default and the DP fails.
    data_product(name="my-semantic-dp", provision_timeout_secs=600, ...)
    # Seeds the base tables + creates the single-table <MODEL>_SEMANTIC view
    # BEFORE promise verification. provision.py is self-contained (no sibling imports).
    .provision(script("provision.py"))
    # Transform = RUNTIME data production (+ it bundles registry.py/tools.py via
    # the **/*.py glob). Write real transform logic if the DP produces data at
    # runtime; for a static-seed DP it's a no-op. It must NEVER (re)provision —
    # seeding/creating the promised table or view here makes the DP flap.
    .transform(code(transform).compute("<infra-profile-path>#/services/<compute>"))
    .output(
        data_product_output()
        .promise(provision_marker)
        # plain storage(...) — NOT .config(...).as_view(...): the facade as_view
        # pattern is mutually exclusive with .transform(), and an rpc DP needs the
        # transform (for sibling bundling). nxd validate rejects facade + transform.
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
- `.provision(script("provision.py"))` seeds + creates the view before verify;
  `.transform(...)` is mandatory (it bundles the sibling modules) and carries any
  runtime data production — but never (re)provisions.
- `.description(t.description)` — chainable; sets the MCP tool description.
- `.enable_endpoints()` — publishes the HTTP+MCP endpoint.
- `.mcp_path("/mcp")` — sets the MCP mount path on the rpc_server port.

**Do NOT use the facade `as_view` storage pattern for an rpc/MCP semantic DP.**
`storage(...).config(SnowflakeConfig().as_view(sql_script(...)))` is mutually
exclusive with `.transform()` — `nxd validate` raises
`Facade view output(s) ... cannot be combined with .transform()` — and an rpc DP
*needs* the transform to bundle `registry.py`/`tools.py`. Seed in `@on_provision`
with a plain `storage(...)` port instead. (The facade pattern is fine for a
pure-storage DP with no rpc tools; it is not an option here.)

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
- **Always declare a `.transform(...)`**: it bundles the sibling `registry.py` /
  `tools.py` modules into the image (`.output(_rpc)` alone ships only the
  extracted tool scripts → `ModuleNotFoundError` at pod startup). Write real
  runtime data-production logic here if the DP has any; for a static-seed DP it is
  a legitimate no-op. The transform must NEVER (re)provision — seeding/creating
  the promised table or view in the transform makes the DP flap `Started`↔`Failed`.
- **Provision is provision-time, not runtime — respect the lifecycle**: promise
  verification runs BEFORE the transform, so the promised table + semantic view
  must be created in `@on_provision` via `.provision(script("provision.py"))`.
  Transform-time setup fails verification (`Field ... not found in the model`).
- **`provision.py` is self-contained**: no sibling imports (it runs from a subdir
  where flat imports don't resolve); hardcode the `<MODEL>_SEMANTIC` view name.
- **The view DDL references only this DP's own tables**: never the compiler's
  cross-DP join DDL — cross-DP joins resolve at query time, not view-create time.
- **Type the rpc `snowflake` param `: Snowflake`** with a module-level import, and
  **never reference a module-level constant from an extracted tool** (inline it).
  Both are rpc-extraction deploy-breakers — see Step 3's two gotchas.
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
