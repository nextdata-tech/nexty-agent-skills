# Semantic-layer data product: overview

## Contents
- What this kit provides
- Two-layer design
- Stopgap status and ADR-020 convergence

---

## What this kit provides

The `semantic/` kit is a self-contained Python library that turns a
**curated semantic registry** (models, dimensions, metrics, joins) into four
governed MCP tools exposed by a Nextdata OS data product:

| Tool | Purpose |
|------|---------|
| `list_metrics` | Enumerate named measures with aggregation + grain |
| `list_dimensions` | Enumerate slicing axes with PII flags |
| `describe_metric` | Show one metric's aggregation, grain, compatible dimensions |
| `run_semantic_query` | Compile a concept selection to SQL, run it, return rows |

An AI agent interacts only with concept names. It never writes SQL. The
compiler enforces correctness (chasm-trap, dimension compatibility) and the
execution path is read-only, aggregated, and capped at 200 rows.

---

## Two-layer design

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 1 — per-DP (author this once per data product)   │
│                                                         │
│  registry.py  ←  SemanticRegistry fluent builder        │
│                   .model() .dimension() .metric()        │
│                   .join() .build()                       │
└────────────────────────────┬────────────────────────────┘
                             │  CompiledRegistry (frozen)
┌────────────────────────────▼────────────────────────────┐
│  LAYER 2 — vendored kit (never re-author)               │
│                                                         │
│  semantic/registry.py    — Agg, Cardinality, Model,     │
│                            Dimension, Metric, Join,      │
│                            SemanticRegistry              │
│  semantic/dialect.py     — Dialect protocol +           │
│                            SnowflakeDialect              │
│  semantic/compiler.py    — compile_selection,           │
│                            chasm-trap defence            │
│  semantic/mcp_tools.py   — build_semantic_tools()        │
└────────────────────────────┬────────────────────────────┘
                             │  build_semantic_tools(REGISTRY)
                             │  → list[SemanticTool]
                             │    (.fn, .request_model, .response_model)
┌────────────────────────────▼────────────────────────────┐
│  LAYER 3 — spec.py RPC output (the real MCP wiring)     │
│                                                         │
│  _rpc = data_product_rpc_output()                       │
│  for t in build_semantic_tools(REGISTRY):               │
│      _rpc = _rpc.function(                               │
│          rpc_function(code(t.fn),                       │
│              t.request_model, t.response_model)         │
│          .description(t.description))                   │
│  _rpc = _rpc.port("mcp-api",                            │
│      rpc_server("<svc>").enable_endpoints()             │
│      .mcp_path("/mcp"))                                  │
│  ... data_product(...).output(_rpc)                     │
└─────────────────────────────────────────────────────────┘
```

The data product author writes only `registry.py`. The compiler, dialect, and
MCP tool factory are shared infrastructure vendored by copying `reference/scripts/semantic/`
verbatim into the DP's `transform/semantic/` directory. NXD discovers the tools
ONLY through the `spec.py` `data_product_rpc_output()` wiring above — there is no
module-level `tools` list; a bare `tools = build_semantic_tools(...)` exposes
nothing.

---

## Stopgap status and ADR-020 convergence

This kit is **module-named `nxd.experimental.semantic`** in the `nxd_py` monorepo to
signal that it is a stopgap. ADR-020 (`docs/architecture/adrs/020-semantic-layer-first-class.md`)
defines the convergence target: first-class `measure` / `dimension` / `grain` in
`nxd.spec` with kernel-driven Snowflake semantic-view capability.

Every public name in the kit (`Agg`, `Cardinality`, `Dimension`, `Metric`,
`Model`, `Join`) is intentionally aligned with ADR-020 so the migration from
`SemanticRegistry.build()` calls to native spec DSL calls is mechanical.

See `reference/adr-020-convergence.md` for the mapping table.
