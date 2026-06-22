# pharma-sites-demo (DP_SITES)

The **MANY_TO_MANY crosswalk hub** of the Fresh Pharma mesh
(`evals/query-loop/MESH_DESIGN.md`). A deployable Nextdata OS semantic-layer
data product exposing governed text-to-SQL over Snowflake via three
model-oriented MCP tools (`list_models`, `describe_model`, `run_semantic_query`),
built on the `nxd.experimental.semantic` library.

## Entities

| Model | Grain | Role |
|-------|-------|------|
| `site_subjects` | `site_id, subject_id` | MANY_TO_MANY crosswalk hub — the fan-out hub. `MANY_TO_ONE -> subjects` (spine, DP_REGISTRY) + `MANY_TO_ONE -> sites`. |
| `sites` | `site_id` | Site dimension — `site_region` (string) dim, `site_count` (COUNT_DISTINCT site_id) metric. |

Entity names are globally unique across the mesh so the bare-name joins
(`subjects`, `sites`) resolve against whichever DP owns them.

## Files

| File | Role |
|------|------|
| `registry.py` | The one per-DP artifact: `SemanticRegistry` (models, dim, metric, the two N:1 crosswalk joins). |
| `tools.py` | Module-level `list_models` / `describe_model` / `run_semantic_query` delegating to the library compiler. |
| `transform.py` | Self-seeds this DP's OWN `SITES` / `SITE_SUBJECTS` base tables (CREATE + INSERT), writes the marker, and provisions a single-table semantic view over them. |
| `models.py` | Single promised marker model (`site_provision_marker`). |
| `spec.py` | Wires transform, plain storage port (NO `as_view`), rpc/MCP output. `INFRA_PROFILE = "ecommerce-demo"`. |
| `requirements.txt` | `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`. |

## Self-seed deploy pattern (NOT facade)

The `.transform(...)` creates and seeds this DP's OWN `SITES` / `SITE_SUBJECTS`
base tables (CREATE TABLE + INSERT) in its own Snowflake schema, writes the
marker, and provisions a single-table semantic view referencing only those
local tables. The storage output port is a plain `storage(...)` with NO
`as_view` — the nxd validator hard-rejects `.transform()` + `as_view()` together,
and the rpc-tool sibling bundling (`**/*.py` glob) only fires when a transform
exists, so self-seed is the only deployable shape.

## Local validation (no cluster)

```bash
PYTHONPATH=. python -c "
from registry import REGISTRY
from nxd.experimental.semantic import build_semantic_tools
from nxd.experimental.semantic.compiler import compile_selection
from nxd.experimental.semantic.dialect import SnowflakeDialect
d = SnowflakeDialect(view_name=SnowflakeDialect.default_view_name(REGISTRY))
print([t.name for t in build_semantic_tools(REGISTRY)])              # 3 tools
print(compile_selection({'measures':['site_count'],'dimensions':['site_region'],'filters':[]},
                        registry=REGISTRY, dialect=d, fqn='DB.SCH.', use_view=True))
"
```
