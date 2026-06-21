# pharma-rx-demo (DP_RX)

Deployable Nextdata OS semantic-layer data product for the fresh pharma mesh
(`MESH_DESIGN.md`). Exposes a governed text-to-SQL semantic layer over pharmacy
**dispenses** via three model-oriented MCP tools (`list_models`,
`describe_model`, `run_semantic_query`), built on `nxd.experimental.semantic`.

## Entity / grain

`dispenses` (grain `DISPENSE_ID`) — MANY dispenses per subject.

| Concept | Kind | Detail |
|---|---|---|
| `dispense_channel` | dimension (string) | fulfilment channel |
| `prescriber_npi` | dimension (string, **PII**) | prescriber NPI |
| `dispense_count` | metric `COUNT_DISTINCT(DISPENSE_ID)` | how many dispenses — **confusable** |
| `units_dispensed` | metric `SUM(UNITS)` | how much dispensed — **confusable** |

Joins (N:1, MANY side is `dispenses`):
- `dispenses ─► site_subjects` on `SUBJECT_ID` (crosswalk hub → spine)
- `dispenses ─► products` on `PRODUCT_ID` (far dimension)

Entity names are globally unique across the mesh so bare-name joins resolve.

## Files

| File | Role |
|------|------|
| `registry.py` | The one per-DP artifact: `SemanticRegistry` (model, dims w/ PII flag, confusable metric pair, two N:1 joins). |
| `tools.py` | Module-level `list_models`/`describe_model`/`run_semantic_query` delegating to the library. |
| `transform.py` | Self-seeds this DP's OWN `DISPENSES` base table + marker + the single-table `DISPENSES_SEMANTIC` view; also makes `registry.py`/`tools.py` get bundled (constraint #2). |
| `models.py` | Single promised marker model. |
| `spec.py` | Wires the plain storage port (NO `as_view`) + rpc/MCP output + transform. |
| `requirements.txt` | `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`. |

## Deploy pattern: SELF-SEED (not facade)

The `.transform(...)` creates and seeds this DP's OWN `DISPENSES` base table
(CREATE TABLE + INSERT), writes the marker, and provisions the single-table
`DISPENSES_SEMANTIC` view over only this DP's own table — all in its own
Snowflake schema. The storage output port is a plain `storage(...)` with NO
`as_view` (the nxd validator hard-rejects `.transform()` + `as_view()` together).

## Local validation (no cluster)

```bash
PYTHONPATH=. python -c "
from registry import REGISTRY
from nxd.experimental.semantic import build_semantic_tools
from nxd.experimental.semantic.compiler import compile_selection
from nxd.experimental.semantic.dialect import SnowflakeDialect
d = SnowflakeDialect(view_name=SnowflakeDialect.default_view_name(REGISTRY))
print([t.name for t in build_semantic_tools(REGISTRY)])              # 3 tools
print(compile_selection({'measures':['units_dispensed'],'dimensions':['dispense_channel'],'filters':[]},
                        registry=REGISTRY, dialect=d, fqn='DB.SCH.', use_view=True))
"
```
