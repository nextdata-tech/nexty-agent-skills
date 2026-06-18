# Runtime and dependencies

## Contents
- Vendored-files approach vs future nxd[rpc] extra
- Exact requirements.txt lines
- Version-skew note
- How the DP runtime discovers the MCP tools

---

## Vendored-files approach vs future nxd[rpc] extra

The `semantic/` kit is currently vendored by copying the files into each DP's
`transform/semantic/` directory. This is intentional: the kit is a stopgap
(see `reference/overview.md`) and the vendoring pattern keeps each DP
self-contained with no transient dependency resolution at runtime.

In a future release, once ADR-026 lands, the kit will be absorbed into
`nxd.spec` and `nxd.drivers.rpc`. At that point the import paths in `spec.py`
will change from `from semantic import ...` to the first-class spec DSL (e.g.
`nxd.spec.measure` / `nxd.spec.dimension`), and the vendored files can be
removed. The migration will be mechanical because all public names are
pre-aligned with ADR-026.

**Do not import from `nxd.experimental.semantic` directly in a generated DP.**
That package path (`nxd.experimental.semantic`) is internal to the `nxd_py`
monorepo. Import from the vendored `semantic` package inside the DP instead
(`from semantic.registry import ...`, `from semantic import build_semantic_tools`).

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
  data_types, script, storage, etc.).
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

## Version-skew note

The vendored `semantic/` files are a **build-time snapshot** of the
`nxd_py` monorepo at a specific commit (recorded in
`reference/scripts/VENDORED_FROM.md`). If `nxd.drivers[rpc]` or
`nxd.data_product[spec]` is bumped to a version that changes the `Request`,
`Response`, `function`, or `mcp` APIs, re-vendor the kit from the updated
monorepo source before deploying.

To check for skew: compare the VENDORED_FROM commit against the installed
`nxd.data_product` version in the DP's running environment. A mismatch
manifests as an `ImportError` or `AttributeError` at DP boot (not at query
time).

---

## How the DP runtime discovers the MCP tools

NXD exposes MCP tools **only** through `spec.py` via `data_product_rpc_output()`.
There is NO module-level `tools` list discovery anywhere. A bare
`tools = build_semantic_tools(REGISTRY)` in any file exposes **zero** MCP tools
at runtime — the NXD kernel never reads that list.

The correct wiring in `spec.py`:

```python
from nxd.spec import data_product_rpc_output, rpc_function, rpc_server, code
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
