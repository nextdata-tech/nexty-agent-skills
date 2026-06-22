# pharma-labs-demo (DP_LABS)

Deployable Nextdata OS semantic-layer data product — **fact #2** of the fresh
pharma mesh (`../../MESH_DESIGN.md`). Models **assays** (grain `assay_id`),
MANY assays per subject, joined `MANY_TO_ONE` to the `site_subjects` crosswalk
hub via `subject_id`.

Exposes three model-oriented MCP tools (`list_models`, `describe_model`,
`run_semantic_query`) over the `nxd.experimental.semantic` library.

## Semantic surface

| Kind | Name | Notes |
|------|------|-------|
| model | `assays` | grain `ASSAY_ID` |
| dimension | `assay_type` (string) | ELISA / PCR / titration |
| metric | `titer_sum` (SUM titer) | **confusable** with `titer_avg` |
| metric | `titer_avg` (AVG titer) | **confusable** with `titer_sum` |
| join | `assays → site_subjects` | `MANY_TO_ONE` on `subject_id` |

`titer_sum` vs `titer_avg` is a deliberate confusable pair — a loosely-worded
"titer level" is ambiguous; the intent gate must disambiguate.

## Files

| File | Role |
|------|------|
| `registry.py` | `SemanticRegistry`: the `assays` model, `assay_type` dim, `titer_sum`/`titer_avg` metrics, the N:1 join. The one authored artifact. |
| `tools.py` | Module-level `list_models`/`describe_model`/`run_semantic_query` delegating to the library compiler. |
| `transform.py` | Self-seeds this DP's OWN `ASSAYS` base table (CREATE + INSERT) + provisions the single-table `ASSAYS_SEMANTIC` view; present so the `**/*.py` glob bundles registry/tools (constraint #2). |
| `models.py` | The promised `assays` model (the self-seeded base table). |
| `spec.py` | Wires plain storage port (NO `as_view`) + transform + rpc/MCP output. `INFRA_PROFILE = "ecommerce-demo"`. |
| `requirements.txt` | `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`. |

## Local validation (no cluster)

```bash
PYTHONPATH=. python -c "
from registry import REGISTRY
from nxd.experimental.semantic import build_semantic_tools
from nxd.experimental.semantic.compiler import compile_selection
from nxd.experimental.semantic.dialect import SnowflakeDialect
d = SnowflakeDialect(view_name=SnowflakeDialect.default_view_name(REGISTRY))
print([t.name for t in build_semantic_tools(REGISTRY)])
print(compile_selection({'measures':['titer_sum'],'dimensions':['assay_type'],'filters':[]},
                        registry=REGISTRY, dialect=d, fqn='DB.SCH.', use_view=True))
"
```

## Deploy pattern

SELF-SEED (mirrors `examples/t2sql-poc/deployable-dp/`): the `.transform(...)`
seeds this DP's OWN `ASSAYS` base table (CREATE + INSERT) and provisions the
single-table `ASSAYS_SEMANTIC` view over it, all in this DP's own Snowflake
schema. The storage output port is a plain `storage(...)` with NO `as_view` —
the nxd validator hard-rejects `.transform()` + `as_view()` together, and the
rpc-tool sibling bundling (`**/*.py` glob) only fires when a transform exists,
so self-seed is the only shape that both bundles siblings AND validates. See the
4 wiring constraints in `../../MESH_DESIGN.md` and the template.
