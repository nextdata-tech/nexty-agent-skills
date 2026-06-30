# Semantic-layer data product: overview

## Contents
- What this kit provides
- How `__nxd_semantic__` annotations flow to the tools
- The four auto-generated tools
- Stopgap status and convergence

---

## What this kit provides

The `nxd.experimental.semantic` library compiles a **curated semantic registry**
(models, dimensions, metrics, joins) into governed, **model-oriented** SQL. Under
the `.semantic_tools()` pattern the author declares the
registry as **per-field `__nxd_semantic__` annotations** on the model attributes;
the kernel compiles them and the single `.semantic_tools(service=...)` spec flag
auto-generates four MCP tools at pod boot.

The author writes a flat set of modules — `models.py` (the annotated models),
`transform.py` (seeds the base tables), `spec.py` (transform + storage port +
`.semantic_tools()`). The compiler, dialect, and tool factory are **imported**
from the installed `nxd.data_product` wheel, never copied.

An AI agent interacts only with concept names. It never writes SQL. The compiler
enforces correctness (chasm-trap, dimension compatibility) and the execution path
is read-only, aggregated, and capped at 200 rows.

---

## How `__nxd_semantic__` annotations flow to the tools

```
models.py                    spec.py build           pod runtime
---------                    -------------           -----------
AttributeSpec._metadata   →  manifest models.yaml →  entrypoints._load_tools()
  __nxd_semantic__: '...'    attributes[*].metadata   │
  (one blob per column)                               │
                                                      ├─ PRIMARY: the kernel
                                                      │  compiles the blobs and
                                                      │  writes one payload per
                                                      │  promised model to
                                                      │  <root>/.nxd/semantic/<model>.json
                                                      │  at boot → glob + merge
                                                      │
                                                      └─ FALLBACK: when no JSON
                                                         files exist (the split-pod
                                                         k8s/rpc topology — the MCP
                                                         server pod runs no kernel),
                                                         _manifest_compile parses the
                                                         bundled models.yaml blobs
                                                         in-process (byte-identical
                                                         payload; needs pyyaml)
                                                      ↓
                                               build_semantic_tools_from_payload()
                                                      ↓
                                               4 MCP tools served at /mcp
```

The author's only job is the **left column**: annotate each model attribute with a
`__nxd_semantic__` blob and **promise the model** on the storage port so its
attributes reach the manifest. Everything to the right is automatic.

> **STOPGAP — the public author API is not yet available.** `AttributeSpec` has no public
> `.semantic_annotation()` setter, so the blob is injected by writing the private
> `_metadata` dict directly via an `_annotate()` helper. Replace with the public
> API once it ships. Keep the injection isolated to `models.py`.

### Why two delivery paths (the split-pod reason)

The MCP server runs in a **separate pod** (`python -m nxd.drivers.rpc.server`,
image `k8s-job-runner`) with a pod-local `emptyDir` `/app` and **no kernel**. The
kernel's `.nxd/semantic/*.json` reach it only when the deployed kernel image
carries the semantic emitter and delivers them into the bundle. The
`_manifest_compile` fallback makes the tools work regardless, by compiling the same
`__nxd_semantic__` blobs from the bundled `models.yaml` (verified byte-identical to
the kernel payload). The fallback needs `pyyaml` — declare it in
`requirements.txt`.

---

## The four auto-generated tools

| Tool | Purpose |
|------|---------|
| `list_models` | Enumerate the semantic models (entities) with grain, metric/dimension counts, and joins |
| `semantic_model` | Return one model's raw registry projection (metrics / dimensions / joins as compiled) |
| `describe_model` | Human-oriented detail for one model: its metrics (each with the dimensions it can be sliced by), its dimensions (with PII flags), and its joins (each naming the reached model and unlocked dimensions) |
| `run_semantic_query` | Compile a concept selection to SQL, run it, return rows |

`describe_model` merges what flat `list_metrics` / `list_dimensions` /
`describe_metric` tools exposed, organised by grain. Because every metric and
dimension lives under one model (one grain), the chasm-trap rule — never combine
metrics from two grains in a single query — is **structural**: you cannot see two
grains' metrics without two `describe_model` calls.

The tools are discovered ONLY through the `.semantic_tools()` spec flag, which
builds the RPC output internally. There is no module-level `tools` list to author,
and you must NOT call `data_product_rpc_output()` yourself — `.semantic_tools()`
raises `ValidationError` if an RPC output already exists.

---

## Stopgap status and convergence

This module is published as **`nxd.experimental.semantic`** (part of the
`nxd_data_product` wheel) and named `experimental` to signal a stopgap. The
convergence target is a future first-class `nxd.spec` measure/dimension DSL:
first-class `measure` / `dimension` / `grain` in `nxd.spec`
with kernel-driven semantic-view capability.

Two migrations are in flight, both mechanical:
- A public `AttributeSpec.semantic_annotation(blob)` setter to
  replace the `_metadata` write. Until it ships, use the `_annotate()` stopgap.
- A native `nxd.spec.measure` / `nxd.spec.dimension` DSL. Every public
  name in the kit (`Agg`, `Cardinality`, `Dimension`, `Metric`, `Model`, `Join`)
  is pre-aligned with it.
