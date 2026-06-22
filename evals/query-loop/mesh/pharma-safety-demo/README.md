# pharma-safety-demo (DP_SAFETY)

Deployable semantic-layer data product for the fresh pharma mesh. Models the
**far adverse-events fact** (`adverse_events`, grain `ae_id`) — MANY adverse
events per subject — and exposes a governed text-to-SQL semantic layer over
Snowflake via three model-oriented MCP tools (`list_models`, `describe_model`,
`run_semantic_query`), built on `nxd.experimental.semantic`.

Mirrors `examples/t2sql-poc/deployable-dp/` file-for-file, with the **self-seed**
deploy pattern (the transform creates + seeds this DP's own base table and the
single-table semantic view; no facade `as_view`).

## Entities

| Model | grain | dimensions | metrics | join |
|---|---|---|---|---|
| `adverse_events` | `AE_ID` | `ae_term` (string) | `ae_count` (COUNT_DISTINCT ae_id), `serious_ae_count` (CASE-SUM `IS_SERIOUS` boolean flag) | MANY_TO_ONE → `site_subjects` on `subject_id` |

`ae_count` vs `serious_ae_count` is a **confusable pair** — `serious_ae_count`
is a `boolean=True` CASE-sum over the `IS_SERIOUS` flag, NOT a numeric SUM. A
loosely-worded "adverse events" must pick `ae_count`; "serious adverse events"
must pick `serious_ae_count`.

The `site_subjects` join target lives in the sibling `pharma-sites-demo` DP; the
bare-name target resolves because entity names are globally unique across the
mesh.

## Files

| File | Role |
|------|------|
| `registry.py` | The one per-DP artifact: `SemanticRegistry` (1 model, 1 dim, 2 metrics, N:1 join). |
| `tools.py` | Module-level `list_models` / `describe_model` / `run_semantic_query` delegating to the library compiler. |
| `transform.py` | Self-seeds this DP's OWN `ADVERSE_EVENTS` base table + marker + a hand-authored single-table `ADVERSE_EVENTS_SEMANTIC` view — and forces the `**/*.py` glob to bundle the registry/tools siblings (constraint #2). |
| `models.py` | The promised `pharma_safety_marker` model (satisfies the storage output port). |
| `spec.py` | Wires the transform, the plain storage port (NO `as_view`), and the rpc/MCP output. |
| `requirements.txt` | `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`. |

## Local validation (no cluster)

```bash
PYTHONPATH=. uv run python -c "
from registry import REGISTRY
from nxd.experimental.semantic import build_semantic_tools
from nxd.experimental.semantic.compiler import compile_selection
from nxd.experimental.semantic.dialect import SnowflakeDialect
d = SnowflakeDialect(view_name=SnowflakeDialect.default_view_name(REGISTRY))
print([t.name for t in build_semantic_tools(REGISTRY)])              # 3 tools
print(compile_selection({'measures':['serious_ae_count'],'dimensions':['ae_term'],'filters':[]},
                        registry=REGISTRY, dialect=d, fqn='DB.SCH.', use_view=True))
"
```

## Wiring constraints

The four non-negotiables from the template apply unchanged: (1) `code()` cannot
extract closures — tools are module-level functions; (2) the registry sibling is
bundled only because a `.transform(...)` is declared; (3) all modules flat at the
DP root, imported flat; (4) base tables are self-seeded by the `.transform(...)`
(CREATE + INSERT into this DP's own schema), and the single-table semantic view
references ONLY this DP's own table.
