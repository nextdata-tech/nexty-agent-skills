# ADR-026 convergence

## Contents
- What ADR-026 proposes
- Mapping table: today's registry calls to ADR-026 spec DSL
- extra_dimensions divergence note
- Migration path

---

## What ADR-026 proposes

ADR-026 (`docs/architecture/adrs/026-semantic-layer-first-class.md` in the
`nxd` monorepo) defines first-class `measure` / `dimension` / `grain` /
`cardinality` support in `nxd.spec` and the NXD kernel, replacing the stopgap
`SemanticRegistry` builder with native spec DSL.

Under ADR-026, a data product author will write:

```python
# Future ADR-026 spec DSL (not yet available)
from nxd.spec import data_product, grain, measure, dimension, join

spec = (
    data_product(...)
    .grain("orders", key="order_id", ...)
    .dimension("region", on="orders", column="REGION")
    .measure("order_count", on="orders", agg="count_distinct", column="order_id")
    .join("orders", "products", on=("product_id", "product_id"),
          cardinality="many_to_one")
)
```

The kernel will own SQL generation and MCP tool exposure natively.

---

## Mapping table: today's registry calls to ADR-026 spec DSL

| Today (SemanticRegistry) | ADR-026 (nxd.spec, future) | Notes |
|--------------------------|---------------------------|-------|
| `.model(name, grain=..., description=...)` | `.grain(name, key=..., description=...)` | `grain` replaces `model` as the primary entity |
| `.dimension(name, model=..., column=..., type=..., pii=...)` | `.dimension(name, on=..., column=..., type=..., pii=...)` | `on` replaces `model` for the owning entity |
| `.metric(name, model=..., agg=..., column=..., boolean=...)` | `.measure(name, on=..., agg=..., column=..., boolean=...)` | `measure` replaces `metric`; `on` replaces `model` |
| `.join(left=..., right=..., on=..., cardinality=...)` | `.join(left=..., right=..., on=..., cardinality=...)` | Identical shape; `Cardinality` enum preserved |
| `Agg.COUNT_DISTINCT` | `Agg.COUNT_DISTINCT` | All six Agg values preserved verbatim |
| `Cardinality.MANY_TO_ONE` | `Cardinality.MANY_TO_ONE` | All four Cardinality values preserved |
| `SemanticRegistry().build()` | implicit in spec `.build()` | Validation rules preserved |
| `build_semantic_tools(registry)` | kernel-native MCP tool exposure | Concept names and tool signatures unchanged |

Public types (`Agg`, `Cardinality`, `Dimension`, `Metric`, `Model`, `Join`,
`CompiledRegistry`) are intentionally named to match ADR-026 so the migration
is a rename of the call site, not a semantic redesign.

---

## extra_dimensions divergence note

The stopgap registry exposes `extra_dimensions` as an explicit override on
`Metric`. ADR-026 derives cross-model dimension reach **exclusively** from the
cardinality-annotated join — there is no per-metric explicit override in the
proposed spec DSL.

This means:

- In the stopgap, an explicit `extra_dimensions=("some_dim",)` overrides
  auto-derivation entirely for that metric.
- Under ADR-026, all reach is derived from joins. There will be no per-metric
  override knob.

**Recommendation**: do not use `extra_dimensions` in new registries unless
the auto-derived set is genuinely wrong and cannot be fixed by correcting the
join. Code using `extra_dimensions` will require a manual review pass during
the ADR-026 migration to verify that the correct reach is expressed via joins
instead.

---

## Migration path

When ADR-026 lands:

1. Replace `from semantic.registry import SemanticRegistry, Agg, Cardinality`
   with `from nxd.spec import grain, measure, dimension, join` (names TBD per
   ADR-026 final spec).
2. Replace `.model(...)` calls with `.grain(...)`.
3. Replace `.metric(...)` calls with `.measure(...)`.
4. Replace `.dimension(..., model=...)` with `.dimension(..., on=...)`.
5. Remove `build()` call — the kernel owns compilation.
6. Remove `from semantic import build_semantic_tools` and `tools = ...` from
   `mcp.py` — the kernel exposes MCP tools natively.
7. Remove the vendored `semantic/` directory and the `nxd.drivers[rpc]`
   requirement.

The migration is mechanical because all concept names (`order_count`, `region`,
`Agg.SUM`, etc.) are unchanged.
