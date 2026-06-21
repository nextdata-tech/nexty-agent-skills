# pharma-visits-demo (DP_VISITS)

Deployable Nextdata OS semantic-layer data product — **fact #1** in the fresh
pharma mesh (`../../MESH_DESIGN.md`). Models clinical **visits** (grain
`visit_id`, MANY visits per subject) and exposes the governed text-to-SQL tools
(`list_models`, `describe_model`, `run_semantic_query`) over MCP via the
`nxd.experimental.semantic` library.

## Semantics

| Item | Value |
|------|-------|
| Model / grain | `visits` (`VISIT_ID`) — MANY visits per subject |
| Dimension | `visit_type` (string) |
| Metric | `visit_count` = `COUNT_DISTINCT(VISIT_ID)` |
| Metric | `visit_duration_min` = `SUM(DURATION_MIN)` |
| Join | `visits` → `site_subjects` MANY_TO_ONE on `SUBJECT_ID` |

**Confusable pair (cross-grain):** `visit_count` (how many visits, this model)
vs `subject_count` (how many subjects, owned by DP_REGISTRY). "How many visits"
must resolve to `visit_count`.

## Files

| File | Role |
|------|------|
| `registry.py` | `SemanticRegistry` — the one authored artifact: model, `visit_type` dim, `visit_count` / `visit_duration_min` metrics, the N:1 join. |
| `tools.py` | Module-level `list_models` / `describe_model` / `run_semantic_query` delegating to the library (constraint #1). Identical to the template. |
| `transform.py` | Self-seeds this DP's OWN `visits` base table (CREATE + INSERT), writes the marker, and provisions the single-table `VISITS_SEMANTIC` view; present so the `**/*.py` glob bundles registry/tools (constraint #2). |
| `models.py` | The promised `pharma_visits_marker` model. |
| `spec.py` | Wires the plain storage port (NO `as_view`), the transform, and the rpc/MCP output. `INFRA_PROFILE = "ecommerce-demo"`. |
| `requirements.txt` | `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`. |

## Deploy pattern: SELF-SEED (not facade)

The `.transform(...)` creates and seeds this DP's OWN `visits` base table
(CREATE TABLE + INSERT), writes the marker, and hand-authors a single-table
`VISITS_SEMANTIC` view over only this DP's own table — all in its own Snowflake
schema. The storage output port is a plain `storage(...)` with NO `as_view` (the
nxd validator hard-rejects `.transform()` + `as_view()` together).

## Local validation (no cluster)

```bash
PYTHONPATH=. python -c "
from registry import REGISTRY
from nxd.experimental.semantic import build_semantic_tools
from nxd.experimental.semantic.compiler import compile_selection
from nxd.experimental.semantic.dialect import SnowflakeDialect
d = SnowflakeDialect(view_name=SnowflakeDialect.default_view_name(REGISTRY))
print([t.name for t in build_semantic_tools(REGISTRY)])              # 3 tools
print(compile_selection({'measures':['visit_duration_min'],'dimensions':['visit_type'],'filters':[]},
                        registry=REGISTRY, dialect=d, fqn='DB.SCH.', use_view=True))
"
```
