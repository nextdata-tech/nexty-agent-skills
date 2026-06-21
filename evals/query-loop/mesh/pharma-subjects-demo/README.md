# pharma-subjects-demo — subject spine

The **subject spine** DP of the fresh pharma mesh (`MESH_DESIGN.md` → `DP_REGISTRY`).
A deployable Nextdata OS semantic-layer data product exposing a governed
text-to-SQL layer over the `subjects` model (grain `SUBJECT_ID`) via three MCP
tools (`list_models`, `describe_model`, `run_semantic_query`), built on
`nxd.experimental.semantic`.

## Semantic shape

- **Model:** `subjects` (grain `SUBJECT_ID`) — the spine every mesh fact fans into.
- **Dimensions:** `subject_country` (string), `subject_mrn` (string, **PII**).
- **Metric:** `subject_count` — `COUNT_DISTINCT(SUBJECT_ID)`.
- **Joins:** none. This DP *is* the spine; the crosswalk + facts live in sibling
  DPs and resolve `subjects` by globally-unique bare name.

## Files (mirrors `examples/t2sql-poc/deployable-dp/`)

| File | Role |
|------|------|
| `registry.py` | The one authored artifact: `SemanticRegistry` — `subjects` model, two dimensions (PII on `subject_mrn`), `subject_count` metric, no joins. |
| `tools.py` | Module-level `list_models` / `describe_model` / `run_semantic_query` delegating to the library compiler (constraint #1). |
| `transform.py` | Self-seeds this DP's OWN `SUBJECTS` base table (CREATE + INSERT), writes the promised marker, and provisions the single-table `SUBJECTS_SEMANTIC` view; present so the registry/tools siblings get bundled (constraint #2). |
| `models.py` | Promised marker model (`subjects_marker`). |
| `spec.py` | Wires transform + plain storage port (NO `as_view`) + rpc/MCP output. `INFRA_PROFILE = "ecommerce-demo"`. |
| `requirements.txt` | `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`. |

## Deploy pattern: SELF-SEED (not facade)

This DP uses the self-seed pattern (mirrors `examples/t2sql-poc/deployable-dp/`):
the `.transform(...)` creates and seeds this DP's OWN `SUBJECTS` base table
(CREATE TABLE + INSERT), writes the marker, and provisions a single-table
`SUBJECTS_SEMANTIC` view over it — all in its own Snowflake schema. The storage
output port is a plain `storage(...)` with NO `as_view` (the nxd validator
hard-rejects `.transform()` + `as_view()` together).

## Local validation (no cluster)

```bash
PYTHONPATH=. python -c "
from registry import REGISTRY
from nxd.experimental.semantic import build_semantic_tools
from nxd.experimental.semantic.compiler import compile_selection
from nxd.experimental.semantic.dialect import SnowflakeDialect
d = SnowflakeDialect(view_name=SnowflakeDialect.default_view_name(REGISTRY))
print([t.name for t in build_semantic_tools(REGISTRY)])              # 3 tools
print(compile_selection({'measures':['subject_count'],'dimensions':['subject_country'],'filters':[]},
                        registry=REGISTRY, dialect=d, fqn='DB.SCH.', use_view=True))
"
```
