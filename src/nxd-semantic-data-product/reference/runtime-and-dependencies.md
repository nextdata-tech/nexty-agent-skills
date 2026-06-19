# Runtime and dependencies

## Contents
- How the semantic module is delivered
- Exact requirements.txt lines
- Pip-registry version requirement
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
- `nxd.drivers[rpc]` — the `nxd.drivers.rpc` module that `mcp_tools.py`
  imports (`Request`, `Response`, `function`, `mcp`).
- `snowflake-connector-python[pandas]` — the Snowflake Python connector with
  pandas result fetching. Required by `mcp_tools.py`'s `run_semantic_query`
  implementation.
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

## How the DP runtime discovers the MCP tools

NXD exposes MCP tools **only** through `spec.py` via `data_product_rpc_output()`.
There is NO module-level `tools` list discovery anywhere. A bare
`tools = build_semantic_tools(REGISTRY)` in any file exposes **zero** MCP tools
at runtime — the NXD kernel never reads that list.

The correct wiring in `spec.py`:

```python
from nxd.spec import data_product_rpc_output, rpc_function, rpc_server, code
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
    data_product(name="...", ...)
    .output(_rpc)
)
```

`build_semantic_tools(REGISTRY)` returns `list[SemanticTool]`. Each
`SemanticTool` carries:
- `.fn` — the `@function`/`@mcp.tool`-decorated callable; pass to `code(t.fn)`.
- `.request_model` — the `SemanticModelSpec` for the request schema; 2nd arg to `rpc_function`.
- `.response_model` — the `SemanticModelSpec` for the response schema; 3rd arg to `rpc_function`.
- `.description` — the MCP tool description string; pass to `.description(t.description)`.

See `reference/scripts/templates/spec_rpc_output.py.tmpl` for full annotation.
