# Semantic-layer data product: overview

## Contents
- What this kit provides
- Two-layer design
- Stopgap status and ADR-026 convergence

---

## What this kit provides

The `nxd.experimental.semantic` library compiles a
**curated semantic registry** (models, dimensions, metrics, joins) into governed,
**model-oriented** SQL. The data product authors a flat set of modules
(`registry.py`, `tools.py`, `transform.py`, `models.py`, `spec.py`) that wire the
library into three MCP tools exposed by a Nextdata OS data product:

| Tool | Purpose |
|------|---------|
| `list_models` | Enumerate the semantic models (entities) with grain, metric/dimension counts, and joins |
| `describe_model` | Full detail for one model: its metrics (each with the dimensions it can be sliced by), its own dimensions (with PII flags), and its joins (each naming the reached model and unlocked dimensions) |
| `run_semantic_query` | Compile a concept selection to SQL, run it, return rows |

`describe_model` merges what flat `list_metrics` / `list_dimensions` /
`describe_metric` tools exposed, organised by grain. Because every metric and
dimension lives under one model (one grain), the chasm-trap rule — never combine
metrics from two grains in a single query — is **structural**: you cannot see two
grains' metrics without two `describe_model` calls.

An AI agent interacts only with concept names. It never writes SQL. The
compiler enforces correctness (chasm-trap, dimension compatibility) and the
execution path is read-only, aggregated, and capped at 200 rows.

---

## Two-layer design

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 1 — per-DP (author once per data product, FLAT)  │
│                                                         │
│  registry.py  ←  SemanticRegistry fluent builder        │
│                   .model() .dimension() .metric()        │
│                   .join() .build()                       │
│  tools.py     ←  module-level list_models /             │
│                   describe_model / run_semantic_query    │
│  transform.py ←  provisions the view (MANDATORY)        │
│  models.py    ←  one promised marker model              │
│  (all FLAT siblings of spec.py — no transform/ subdir)  │
└────────────────────────────┬────────────────────────────┘
                             │  CompiledRegistry (frozen)
┌────────────────────────────▼────────────────────────────┐
│  LAYER 2 — nxd.experimental.semantic (installed wheel)  │
│                                                         │
│  Agg, Cardinality, Model, Dimension, Metric, Join,      │
│  SemanticRegistry, CompiledRegistry, CompileError        │
│  compile_selection, SnowflakeDialect, Dialect,           │
│  build_semantic_tools, SemanticTool                      │
│                                                         │
│  (provided by nxd_data_product >= 0.41.90)              │
└────────────────────────────┬────────────────────────────┘
                             │  build_semantic_tools(REGISTRY)
                             │  → list[SemanticTool]
                             │    (.request_model, .response_model, .description)
                             │    used ONLY for schemas — NOT for the callable
┌────────────────────────────▼────────────────────────────┐
│  LAYER 3 — spec.py RPC output (the real MCP wiring)     │
│                                                         │
│  from tools import list_models, describe_model,         │
│                    run_semantic_query   # module-level  │
│  _map = {t.name: t for t in                             │
│          build_semantic_tools(REGISTRY)}                │
│  _rpc = data_product_rpc_output()                       │
│  for fn, name in [(list_models,"list_models"), ...]:    │
│      t = _map[name]                                      │
│      _rpc = _rpc.function(                               │
│          rpc_function(code(fn),       # module-level fn │
│              t.request_model, t.response_model)         │
│          .description(t.description))                   │
│  _rpc = _rpc.port("mcp-api",                            │
│      rpc_server("<svc>").enable_endpoints()             │
│      .mcp_path("/mcp"))                                  │
│  data_product(...).transform(code(transform)...)        │
│                  .output(_rpc)        # transform = must│
└─────────────────────────────────────────────────────────┘
```

The data product author writes `registry.py`, plus a flat `tools.py`
(module-level `list_models` / `describe_model` / `run_semantic_query`) and a
mandatory `transform.py`. The compiler, dialect, and MCP tool factory are
provided by the installed `nxd.experimental.semantic` library (shipped in the
`nxd_data_product` wheel) — imported, not copied.

Two non-obvious wiring constraints (Layer 3):
- **`code()` cannot extract closures.** `build_semantic_tools(REGISTRY)` returns
  closures (`build_semantic_tools.<locals>.list_models`) — `code()`'s
  `inspect.getsource` can't locate them. Pass `code(<module-level tools.py fn>)`;
  reuse `build_semantic_tools(...)` ONLY for `.request_model` / `.response_model`
  / `.description`.
- **A `.transform(...)` is mandatory.** The rpc-output `code()` path ships only
  the extracted tool scripts; the `**/*.py` glob on the transform path is what
  bundles the sibling `registry.py` / `tools.py` modules into the image. Without
  the transform the pod dies with `ModuleNotFoundError: No module named
  'registry'`.

NXD discovers the tools ONLY through the `spec.py` `data_product_rpc_output()`
wiring above — there is no module-level `tools` list; a bare
`tools = build_semantic_tools(...)` exposes nothing.

---

## Stopgap status and ADR-026 convergence

This module is published as **`nxd.experimental.semantic`** (part of the
`nxd_data_product` wheel, >= 0.41.90) and named `experimental` to signal that it
is a stopgap. ADR-026 (`docs/architecture/adrs/026-semantic-layer-first-class.md`)
defines the convergence target: first-class `measure` / `dimension` / `grain` in
`nxd.spec` with kernel-driven Snowflake semantic-view capability.

Every public name in the kit (`Agg`, `Cardinality`, `Dimension`, `Metric`,
`Model`, `Join`) is intentionally aligned with ADR-026 so the migration from
`SemanticRegistry.build()` calls to native spec DSL calls is mechanical.
