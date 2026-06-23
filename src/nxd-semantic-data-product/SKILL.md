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
  version: 0.5.0
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

**Two extraction gotchas the rpc tool path WILL trip — both are deploy-breakers:**

1. **Type the storage-context param with its SPECIFIC driver handle (NOT untyped / `Any`), via a MODULE-LEVEL import.** The rpc runtime injects the non-`request` arg **by type**: a param typed with the driver context class (`Snowflake`, `Databricks`, `BigQuery` — whatever the storage port provides) gets a real handle; an untyped / `Any` param gets a raw `Context` with no driver methods and `run_semantic_query` fails live (`'Context' object has no attribute ...`). Import the concrete type at module level so `code()` + `get_type_hints` resolve the annotation in the rpc subprocess.

2. **Never reference a module-level constant from inside an extracted tool** — inline it. `code()` carries a tool's imports + the `def`/`class` it calls, but **drops module-level `=` assignments**. A module-level `_DESC = "..."` (in `@mcp.tool(description=_DESC)`) or `_DIALECT = SnowflakeDialect(...)` raises `NameError` at rpc-server load → 0 tools registered → `nxd mcp health` shows the DP `Broken`/`tool_count: 0`. Inline the description literals; build the dialect **inside** the function body.

### Step 4 — Provision the tables + views (`@on_provision`), seed data in the transform

This is the single most error-prone part of a semantic DP. Split the work by responsibility across two lifecycle stages:

- **`provision.py` (`@on_provision` hook) — DDL ONLY.** Creates the SOURCE TABLE STRUCTURE(s) and the single-table semantic VIEW(s). No data. Idempotent: `CREATE TABLE IF NOT EXISTS`, `CREATE OR REPLACE VIEW`. Runs in **Phase A, BEFORE the transform.**
- **`transform.py` — DATA ONLY.** Seeds the rows (`TRUNCATE TABLE IF EXISTS` + `write_pandas`). **No DDL** — never `CREATE TABLE`, never `CREATE VIEW`. A transform that RE-PROVISIONS (`CREATE OR REPLACE TABLE` each run) is what made DPs flap Started ↔ Failed.

Kernel ordering is **provision → transform → output-port-promise-verification** (the promise is checked after each model completes). So the provision hook creates the empty table + view; the transform fills the rows; the promise then verifies the rows are present. The DP deploys green in one launch. The semantic VIEW is **single-table** (references only THIS DP's own tables); cross-DP joins resolve at QUERY time via the live mesh, never in the view DDL.

**(a) PROVISION the table structure(s) + view in `provision.py`.** The hook is
decorated `@data_product.on_provision()` and takes a param named for the storage
output port (e.g. `snowflake: Snowflake`), injected as a typed driver handle.
Create the promised model's managed table with `CREATE TABLE IF NOT EXISTS`
against `snowflake.full_table_name("<model>")` (the *exact* table the storage
driver verifies the promise against), then `CREATE OR REPLACE VIEW` the
single-table `<MODEL>_SEMANTIC` view over it. A trailing
`if __name__ == "__main__":` guard is **required** — a registered-but-never-invoked
lifecycle hook is a hard `ValidationError` at build time, not a silent no-op.

```python
# provision.py — DDL ONLY: table structure(s) + single-table semantic view.
from nxd import data_product
from nxd.data_product.context import Snowflake   # type the param with the SPECIFIC driver handle

_VIEW_NAME = "SUBJECTS_SEMANTIC"   # = SnowflakeDialect.default_view_name(REGISTRY) for model `subjects`

@data_product.on_provision()
def provision(snowflake: Snowflake) -> None:
    from snowflake import connector
    if snowflake is None or not snowflake.schema:
        return
    fqn = (f"{snowflake.database}.{snowflake.schema}."
           if snowflake.database else f"{snowflake.schema}.")
    conn = connector.connect(  # user/account/warehouse/role/database/schema +
        ocsp_fail_open=True, **snowflake.connector_params(),  # ...from the handle
        user=snowflake.user, account=snowflake.account, warehouse=snowflake.warehouse,
        role=snowflake.role, database=snowflake.database, schema=snowflake.schema,
    )
    try:
        cur = conn.cursor()
        # 1) PROMISED model's managed table — structure only, no rows.
        managed = snowflake.full_table_name("subjects")
        cur.execute(f"CREATE TABLE IF NOT EXISTS {managed} "
                    "(SUBJECT_ID NUMBER, SUBJECT_COUNTRY VARCHAR, SUBJECT_MRN VARCHAR)")
        # 2) Single-table semantic view over it (NO cross-DP JOIN).
        cur.execute(f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS "
                    "SELECT SUBJECT_ID, SUBJECT_COUNTRY, SUBJECT_MRN "
                    f"FROM {managed}")
    finally:
        conn.close()

if __name__ == "__main__":
    data_product.provision()
```

**(b) SEED the data in `transform.py` — no DDL.** The transform receives the same
storage handle (param name = the storage port name). The table already exists from
the provision hook, so the transform only refreshes rows: `TRUNCATE TABLE IF
EXISTS` (keeps repeated runs deterministic) then `write_pandas`. **Never** issue
`CREATE TABLE` or `CREATE VIEW` here — a re-provisioning transform is what made DPs
flap.

```python
# transform.py — DATA ONLY: truncate-and-load the rows. NO DDL.
# Also bundles registry.py/tools.py/provision.py (the **/*.py glob runs on the
# transform/compute path).
import pandas as pd
from nxd.data_product.context import Snowflake

def transform(snowflake: Snowflake) -> None:
    from snowflake import connector
    from snowflake.connector.pandas_tools import write_pandas
    if snowflake is None or not snowflake.schema:
        return
    rows = pd.DataFrame([
        {"SUBJECT_ID": 1, "SUBJECT_COUNTRY": "US", "SUBJECT_MRN": "MRN-0001"},
        {"SUBJECT_ID": 2, "SUBJECT_COUNTRY": "DE", "SUBJECT_MRN": "MRN-0002"},
    ])
    conn = connector.connect(  # same connect(...) args as provision.py above
        user=snowflake.user, account=snowflake.account, warehouse=snowflake.warehouse,
        role=snowflake.role, database=snowflake.database, schema=snowflake.schema,
        ocsp_fail_open=True, **snowflake.connector_params(),
    )
    try:
        managed = snowflake.full_table_name("subjects")  # table the provision hook created
        cur = conn.cursor()
        try:
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")  # NO CREATE TABLE / CREATE VIEW here
        finally:
            cur.close()
        write_pandas(conn, rows, managed.split(".")[-1].strip('"'),
                     database=snowflake.database, schema=snowflake.schema)
    finally:
        conn.close()
```

**(c) The `.transform(...)` is mandatory** — the rpc-output `code(fn)` path ships only the extracted `__<fn>__.py` tool scripts, NOT the sibling modules they import (`registry.py`, `tools.py`, `provision.py`); those are bundled by the `**/*.py` glob that runs on the transform/compute output path. Without a `.transform(...)` the pod dies `ModuleNotFoundError: No module named 'registry'`.

**(d) The view DDL must reference ONLY this DP's own tables.** Never call the compiler's `native_semantic_view_ddl` / `plain_view_ddl` when the registry declares a cross-DP join — those emit a JOIN to a table in ANOTHER DP's schema, so `CREATE VIEW` binds a missing object and provisioning fails. Hand-author a **single-table** `<MODEL>_SEMANTIC` view. For a multi-table DP (e.g. a crosswalk hub that owns its own dimension), the view may `LEFT JOIN` THIS DP's own tables — but never another DP's schema. Cross-DP joins resolve at QUERY time via the live mesh, never at view-creation time.

**(e) Raise the compute startup timeout for heavy deps + cold-boot contention.** A cold compute boot builds `snowflake-connector-python[pandas]`+pandas; under mesh-wide launch contention this blows past the default → `Timeout waiting for execution to start` → DP `Failed`. Set `.startup_timeout(600)` on the **transform** (a method on the compute spec — NOT a factory kwarg). **Do NOT put `.startup_timeout(...)` on `.provision(...)`** — the validator raises `ValidationError`; provision inherits the transform executor's budget.

**(f) Promise the REAL model, not a marker.** `.promise(<model>)` with the actual `semantic_model(...)` (authored in `models.py`) so the discover UI surfaces its attributes, PII flags, glossary links, and — on downstream facts — the cross-DP semantic relationship. See Step 5 for the model + lineage forms.

NXD exposes MCP tools **only** through `spec.py` via `data_product_rpc_output()`.
There is NO module-level `tools` list discovery — a bare
`tools = build_semantic_tools(REGISTRY)` in any file exposes **zero** MCP tools.
Add the block below to your `spec.py` (see
`reference/scripts/templates/spec_rpc_output.py.tmpl` for the fully annotated
form and `transform_provision.py.tmpl` for a complete example):

```python
from nxd.spec import (  # NB: `script` is required for .provision(script("provision.py"))
    code, data_product, data_product_output, data_product_rpc_output,
    Predicate, rpc_function, rpc_server, script, storage,
)
from nxd.experimental.semantic import build_semantic_tools
from registry import REGISTRY
from tools import list_models, describe_model, run_semantic_query
from transform import transform
from models import subjects_model   # the REAL promised semantic_model (see Step 5)

INFRA_PROFILE = "<infra-profile-name>"

# build_semantic_tools(REGISTRY) → only the tools' request/response schemas +
# descriptions; the callable passed to code() is the module-level tools.py fn.
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
    rpc_server(f"/infra-profile/{INFRA_PROFILE}#/services/<mcp-service-name>")
    .enable_endpoints()
    .mcp_path("/mcp"),
)

# Plain storage(...) — NOT .config(...).as_view(...): facade as_view is mutually
# exclusive with .transform(), and an rpc DP needs the transform for bundling.
_storage = (
    data_product_output()
    .promise(subjects_model)   # promise the REAL model so the UI surfaces attrs + glossary
    .port("snowflake", storage(f"/infra-profile/{INFRA_PROFILE}#/services/<snowflake>"))
)

spec = (
    data_product(name="my-semantic-dp", domain="...", version="1.0.0-dev",
                 infra_profile=INFRA_PROFILE)
    # PROVISION (Phase A, before the transform): the @on_provision hook creates the
    # table STRUCTURE + single-table semantic VIEW (DDL only). IMMEDIATELY BEFORE
    # .transform(...). NO .startup_timeout(...) here — the validator rejects it.
    .provision(
        script("provision.py")
        .compute(f"/infra-profile/{INFRA_PROFILE}#/services/<compute>")
    )
    # TRANSFORM: seeds the rows (truncate-and-load, NO DDL) into the table the
    # provision hook created, and bundles registry.py / tools.py / provision.py via
    # the **/*.py glob. The promise is verified AFTER the transform.
    .transform(
        code(transform)
        .compute(f"/infra-profile/{INFRA_PROFILE}#/services/<compute>")
        .startup_timeout(600)
    )
    .output(_storage)
    .output(_rpc)
    # Glossary links tie this DP's terms to the governed glossary DP (see Step 5).
    .link(Predicate.GlossaryTerm, "/data-product/<env>/<glossary-dp>#/terms/<term>")
)
```

Key facts:
- The tool callable passed to `code(_fn)` is the **module-level** function from
  `tools.py` — never `build_semantic_tools(...)[i].fn` (a closure `code()` can't
  extract). `build_semantic_tools(REGISTRY)` is reused ONLY for each tool's
  `.request_model` / `.response_model` / `.description`.
- `rpc_function(code(fn), request_model, response_model)` — all three positional
  arguments are required.
- `.provision(script("provision.py").compute(...))` creates the table + view (DDL)
  and is placed IMMEDIATELY BEFORE `.transform(...)`; the transform seeds the rows;
  promise verification runs *after* the transform.
- `.startup_timeout(600)` is a method on the compute spec — NOT a factory
  `provision_timeout_secs` kwarg (that doesn't exist on the wheel). It goes on
  `.transform(...)` ONLY; the validator raises `ValidationError` on `.provision(...)`.
- `.enable_endpoints()` publishes the HTTP+MCP endpoint; `.mcp_path("/mcp")` sets
  the MCP mount path; `.description(t.description)` sets the MCP tool description.

**Do NOT use the facade `as_view` storage pattern for an rpc/MCP semantic DP.**
`storage(...).config(SnowflakeConfig().as_view(sql_script(...)))` is mutually
exclusive with `.transform()` (`nxd validate` raises `Facade view output(s) ...
cannot be combined with .transform()`), and an rpc DP *needs* the transform to
bundle its siblings. Use a plain `storage(...)` port + the provision-hook/transform
split instead. (The facade is fine for a pure-storage DP with no rpc tools.)

Add to `requirements.txt`:

```
nxd.data_product[spec]
nxd.drivers[rpc]
snowflake-connector-python[pandas]
pandas
```

See `reference/runtime-and-dependencies.md` for version and registry notes.

---

### Step 5 — Author `models.py`: the promised model, glossary links, and cross-DP lineage

`.promise(...)` takes a real `semantic_model(...)` authored in `models.py`. The
model's schema names the promised table's columns; its `.link(...)` calls attach
governed glossary terms (model-level and per-attribute); and `.referencing(...)`
on an attribute declares a cross-DP foreign key that the discover UI renders as a
SEMANTIC RELATIONSHIP.

```python
# models.py
from nxd.spec import Predicate, attribute, semantic_model
from nxd.spec.data_types import int64, string

subjects_model = (
    semantic_model("subjects")
    .description("Subject spine — one row per enrolled clinical-trial subject.")
    .schema({
        "SUBJECT_ID": int64(),
        "SUBJECT_COUNTRY": string(),
        "SUBJECT_MRN": string(),                      # PII
    })
    # Glossary links: model-level, then per-attribute (by attribute name).
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/subject")
    .link("SUBJECT_COUNTRY", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/subject_country")
)
```

**Cross-DP FK (a downstream fact referencing an upstream spine).** Use
`attribute(<type>, "<COL>").referencing(data_product=, model=, attribute=[...])`
in the schema, and declare the runtime dependency with `.input(...).source(...)`
in `spec.py` (placed BEFORE `.transform()`):

```python
# models.py (downstream) — SUBJECT_ID is a cross-DP FK to the subject spine.
"SUBJECT_ID": attribute(int64(), "SUBJECT_ID").referencing(
    data_product="pharma-subjects-demo", model="subjects", attribute=["SUBJECT_ID"]),
```

```python
# spec.py (downstream) — declare the upstream→downstream lineage edge.
.input(
    "pharma-subjects-demo",
    data_product_input()
    .source("https://<host>/data-product/<domain>/pharma-subjects-demo#/output/port/snowflake")
    .environment("demo"),
)
```

The `.input(...)` makes the dependency real (lineage in discover); the
`.referencing(...)` makes the FK render as a semantic relationship. Cross-DP joins
still resolve at QUERY time via the live mesh — the downstream transform seeds only
its own tables and a single-table view (Step 4c).

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
- **Always declare a `.transform(...)`**: it both SEEDS the promised table's rows
  AND bundles the sibling `registry.py` / `tools.py` / `provision.py` modules
  into the image (`.output(_rpc)` alone ships only the extracted tool scripts →
  `ModuleNotFoundError` at pod startup).
- **DDL in `@on_provision`, data in the transform**: the `@on_provision` hook
  (`provision.py`, wired via `.provision(script("provision.py").compute(...))`
  immediately before `.transform(...)`) creates the table STRUCTURE
  (`CREATE TABLE IF NOT EXISTS`) + single-table semantic VIEW
  (`CREATE OR REPLACE VIEW`); the transform seeds only the ROWS (`TRUNCATE TABLE
  IF EXISTS` + `write_pandas`). Kernel order is provision → transform → promise
  verification. Target `snowflake.full_table_name("<model>")` in BOTH so the
  produce-verification target matches. **The transform must NEVER issue DDL** — a
  transform that re-provisions (`CREATE OR REPLACE TABLE` each run) is what made
  DPs flap Started ↔ Failed. `provision.py` needs a trailing
  `if __name__ == "__main__":\n    data_product.provision()` guard, or the build
  raises a `ValidationError`.
- **`.startup_timeout(...)` goes on `.transform(...)`, never `.provision(...)`**:
  the validator raises `ValidationError` if chained on a provision script.
- **Promise the REAL model, not a marker**: `.promise(<semantic_model>)` so the
  discover UI surfaces attributes, PII, glossary links, and cross-DP relationships.
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
| `reference/scripts/templates/transform_provision.py.tmpl` | Complete spec.py + tools.py + provision.py + transform.py wiring (flat layout, module-level tools, provision-DDL / transform-data split) |
| `reference/scripts/scaffold_semantic_dp.py` | Scaffold automation (writes flat registry/tools/transform/models/spec stubs, prints requirements) |

---

## Consuming the deployed DP

This skill is the **producer** side — it builds the semantic-layer DP and its
three MCP tools. To **query** a deployed one (natural-language question → concept
selection → governed SQL), use the **nxd-data-product-query** skill: its §6d
"Semantic-layer MCP ports" drives the `list_models` / `describe_model` /
`run_semantic_query` discover→select→run protocol and the grain-safety (chasm-trap)
recovery against a live mesh.
