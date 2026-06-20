# Runtime and dependencies

## Contents
- How the semantic module is delivered
- Exact requirements.txt lines
- Pip-registry version requirement
- Matched version set across core / drivers / data_product
- Base tables must exist before promise verification
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

## Base tables must exist before promise verification

The kernel runs **promise verification before the transform** on the rpc-output
path. A semantic DP that seeds its own base tables in the transform fails
verification — the tables don't exist yet when verification runs. Two options:

- **Facade over pre-existing tables (recommended for production).** The base
  tables are loaded externally (another DP / pipeline). Reference them via
  `source_aligned_input(...)` and provision the semantic view with
  `storage(...).config(SnowflakeConfig().as_view(sql_script(...)))`, which runs
  at **provision time** (before verification). See
  `examples/features/drivers/snowflake-storage/snowflake-source-aligned-facade/`
  in the nxd repo.
- **Self-seed (self-contained demo only).** The transform seeds the base tables.
  A pure post-verify transform-seed will NOT pass verification in a single launch
  — the promised marker model passes, but a contract that reads the seeded query
  tables would fail on the first run. Seed at provision time (or accept the
  first-launch verification gap) for a fully-green deploy.

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
    rpc_function, rpc_server, storage, code,
)
from nxd.experimental.semantic import build_semantic_tools
from registry import REGISTRY
from tools import list_models, describe_model, run_semantic_query
from transform import transform
from models import provision_marker

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
    rpc_server("<infra-profile-path>#/services/<mcp-service-name>")
    .enable_endpoints()
    .mcp_path("/mcp"),
)

spec = (
    data_product(name="...", ...)
    # MANDATORY — bundles the sibling registry.py / tools.py modules.
    .transform(code(transform).compute("<infra-profile-path>#/services/<compute>"))
    .output(
        data_product_output()
        .promise(provision_marker)
        .port("snowflake", storage("<infra-profile-path>#/services/<snowflake>"))
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

See `reference/scripts/templates/spec_rpc_output.py.tmpl` for full annotation and
`reference/scripts/templates/transform_provision.py.tmpl` for the complete
spec.py + tools.py + transform.py example.
