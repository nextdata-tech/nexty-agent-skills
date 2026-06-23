# Runtime and dependencies

## Contents
- How the semantic module is delivered
- Exact requirements.txt lines
- Pip-registry version requirement
- Matched version set across core / drivers / data_product
- Provision creates the tables + views; the transform seeds the data
- How the DP runtime discovers the MCP tools

---

## How the semantic module is delivered

The compiler, dialect, and MCP tool factory (`build_semantic_tools`) are
provided by the installed `nxd.data_product` wheel as the importable package
`nxd.experimental.semantic`. The DP does **not** copy or embed the kit — it
imports it from the environment at runtime, exactly like any other library.

The `experimental` namespace signals a stopgap: once ADR-026 lands, the public
names will migrate into the first-class `nxd.spec` DSL. When that happens the
import paths in `spec.py` will change mechanically (all public names are already
pre-aligned with ADR-026). Until then, import from `nxd.experimental.semantic`.

Import examples:

```python
from nxd.experimental.semantic import (
    Agg, Cardinality, Dimension, Metric, Model, Join,
    SemanticRegistry, CompiledRegistry, CompileError,
    compile_selection, build_semantic_tools, SemanticTool,
    SnowflakeDialect, Dialect,
)
```

All public names listed above are re-exported from the package root; you never
need to import from submodules.

---

## Exact requirements.txt lines

Add these four lines to the DP's `requirements.txt`:

```
nxd.data_product[spec]
nxd.drivers[rpc]
snowflake-connector-python[pandas]
pandas
```

- `nxd.data_product[spec]` — the NXD Python SDK spec extras (semantic_model,
  data_types, script, storage, etc.). Also ships `nxd.experimental.semantic`.
- `nxd.drivers[rpc]` — the `nxd.drivers.rpc` module that
  `nxd.experimental.semantic`'s MCP tool factory imports (`Request`, `Response`,
  `function`, `mcp`).
- `snowflake-connector-python[pandas]` — the Snowflake Python connector with
  pandas result fetching. Required by the library's `run_semantic_query`
  tool implementation.
- `pandas` — explicit pin ensures the pandas extras are satisfied consistently
  across Python versions.

If your DP already declares `nxd.data_product[spec]` in `requirements.txt`,
add only the remaining three lines. Do not duplicate entries.

---

## Pip-registry version requirement

`nxd.experimental.semantic` shipped in **`nxd_data_product >= 0.41.90`**.

Before deploying a semantic DP, confirm the environment's pip registry serves a
wheel at or above that version:

```bash
# Check what the registry serves (substitute your registry URL):
pip index versions nxd.data_product --index-url <pip-registry-url>
```

If the registry is older than 0.41.90, the `import nxd.experimental.semantic`
will fail at DP install time (not at query time). Promote or refresh the pip
registry to a wheel `>= 0.41.90` before launching the DP.

---

## Matched version set across core / drivers / data_product

`nxd_core`, `nxd_drivers`, and `nxd_data_product` must be a **matched version
set** — all three at the same version. The Rust context bindings (`Snowflake`,
`connector_params()`, etc.) are shared across the three wheels; a stale
`nxd_core` against a newer `nxd_data_product` drifts the bindings and fails at
**runtime** with:

```
Error deserializing context: missing field secret_password
```

This is not a registry/import error — the DP installs and starts, then the tool
or transform crashes the first time it deserializes the injected context. If you
refresh the pip registry, rebuild and publish ALL THREE wheels together (e.g.
`make -C components/nxd_py fast-build-multi-arch`), not just the
`nxd_data_product` wheel.

---

## Provision creates the tables + views; the transform seeds the data

The kernel ordering is **provision → transform → output-port-promise-verification**
(the promise is checked after each model completes). So an `@on_provision` hook
creates the empty table + view in Phase A, the transform fills the rows, and the
promise then verifies the rows are present. The DP deploys green in a single
launch.

This is the proven, deployed pattern. Split the work by responsibility:

- **`provision.py` (`@on_provision` hook) — DDL ONLY.** Wired via
  `.provision(script("provision.py").compute(...))`, placed IMMEDIATELY BEFORE
  `.transform(...)`. It `CREATE TABLE IF NOT EXISTS`es the promised model's
  managed table via `snowflake.full_table_name("<model>")` (the EXACT table the
  storage driver verifies the promise against) and `CREATE OR REPLACE VIEW`s the
  single-table `<MODEL>_SEMANTIC` view over it. The hook is decorated
  `@data_product.on_provision()` and needs a trailing
  `if __name__ == "__main__":\n    data_product.provision()` guard, or the build
  raises a `ValidationError` (a registered-but-never-invoked lifecycle hook is a
  hard error). It takes a param named for the storage output port (e.g.
  `snowflake: Snowflake`), injected as a typed driver handle.
- **`transform.py` — DATA ONLY.** Seeds the rows into the table the provision hook
  created: `TRUNCATE TABLE IF EXISTS` + `write_pandas`. It NEVER issues DDL — a
  transform that re-provisions (`CREATE OR REPLACE TABLE` each run) is what made
  DPs flap Started ↔ Failed. Target the same `snowflake.full_table_name("<model>")`
  so produce-verification matches.
- **Promise the REAL model** on a PLAIN `storage(...)` port (no marker, no
  `as_view`). `.startup_timeout(600)` goes on the **transform** compute spec (a
  method, NOT a `provision_timeout_secs` factory kwarg, which does not exist on the
  installed wheel) — and NEVER on `.provision(...)`, where the validator raises a
  `ValidationError`. Provision inherits the transform executor's startup budget.
- **Facade over pre-existing tables (alternative for production data).** If the
  base tables are loaded externally (another DP / pipeline) and you do NOT need a
  `.transform()` to bundle registry.py/tools.py, you may reference them via
  `source_aligned_input(...)` + `storage(...).config(SnowflakeConfig().as_view(...))`.
  But the facade `as_view` is MUTUALLY EXCLUSIVE with `.transform()`, and an rpc
  DP needs the transform to bundle its sibling modules — so for a semantic rpc DP
  the provision-hook/transform split above is the one to use.

---

## How the DP runtime discovers the MCP tools

NXD exposes MCP tools **only** through `spec.py` via `data_product_rpc_output()`.
There is NO module-level `tools` list discovery anywhere. A bare
`tools = build_semantic_tools(REGISTRY)` in any file exposes **zero** MCP tools
at runtime — the NXD kernel never reads that list.

The correct wiring in `spec.py` — note the callable passed to `code()` is a
**module-level** function from `tools.py`, NOT `t.fn` (a closure `code()` cannot
extract):

```python
from nxd.spec import (
    data_product, data_product_output, data_product_rpc_output,
    rpc_function, rpc_server, script, storage, code,
)
from nxd.experimental.semantic import build_semantic_tools
from registry import REGISTRY
from tools import list_models, describe_model, run_semantic_query
from transform import transform
from models import subjects_model   # your REAL semantic model

INFRA_PROFILE = "<infra-profile-name>"

# build_semantic_tools(REGISTRY) is used ONLY for the request/response schemas
# and descriptions — never for the callable.
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

spec = (
    data_product(name="...", infra_profile=INFRA_PROFILE)
    # PROVISION (Phase A, before the transform): the @on_provision hook creates the
    # table STRUCTURE (CREATE TABLE IF NOT EXISTS via snowflake.full_table_name)
    # + the single-table view (DDL only). Placed IMMEDIATELY BEFORE .transform().
    # NO .startup_timeout(...) here — the validator rejects it on .provision().
    .provision(
        script("provision.py")
        .compute(f"/infra-profile/{INFRA_PROFILE}#/services/<compute>")
    )
    # MANDATORY — the transform seeds the ROWS (TRUNCATE + write_pandas, NO DDL)
    # into the table the provision hook created, AND bundles the sibling
    # registry.py / tools.py / provision.py modules. Promise verification runs
    # AFTER the transform, so this seeds green in one launch. .startup_timeout(600)
    # is a METHOD on the compute spec — there is no provision_timeout_secs factory
    # kwarg on the installed wheel.
    .transform(
        code(transform)
        .compute(f"/infra-profile/{INFRA_PROFILE}#/services/<compute>")
        .startup_timeout(600)
    )
    .output(
        data_product_output()
        .promise(subjects_model)   # the REAL model, NOT a marker
        .port("snowflake", storage(f"/infra-profile/{INFRA_PROFILE}#/services/<snowflake>"))
    )
    .output(_rpc)
)
```

`build_semantic_tools(REGISTRY)` returns `list[SemanticTool]`. Each
`SemanticTool` carries:
- `.fn` — the library's closure callable. **Do NOT pass this to `code()`** — it
  is a closure (`build_semantic_tools.<locals>.list_models`) and
  `inspect.getsource` cannot locate it, so the pod never builds. Use the
  module-level function from `tools.py` instead.
- `.request_model` — the `SemanticModelSpec` for the request schema; 2nd arg to `rpc_function`.
- `.response_model` — the `SemanticModelSpec` for the response schema; 3rd arg to `rpc_function`.
- `.description` — the MCP tool description string; pass to `.description(t.description)`.

See `reference/scripts/templates/spec_rpc_output.py.tmpl` for the fully annotated
spec.py wiring, and `transform_provision.py.tmpl` for the complete
provision.py / transform.py / spec.py / tools.py / models.py reference.
