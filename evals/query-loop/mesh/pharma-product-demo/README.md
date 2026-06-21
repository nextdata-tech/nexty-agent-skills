# pharma-product-demo (DP_PRODUCT)

Deployable Nextdata OS semantic-layer data product for the fresh pharma mesh.
Models the **`products`** entity (grain `product_id`) — a **far dimension**,
reachable multi-hop only (`dispenses -> products`). This DP is a **ONE-side
target**: it has **no outgoing joins**. The inbound N:1 join is declared by
DP_RX (`dispenses -> products`); here we model only the product entity so the
bare name `products` resolves across the mesh.

Exposes the three model-oriented MCP tools (`list_models`, `describe_model`,
`run_semantic_query`) over Snowflake via the `nxd.experimental.semantic` library.

## Semantic surface

| Kind | Name | Detail |
|------|------|--------|
| model | `products` | grain `PRODUCT_ID` |
| dimension | `product_name` | string |
| dimension | `modality` | string |
| metric | `product_count` | `COUNT_DISTINCT(PRODUCT_ID)` |

No joins (leaf / far dimension).

## Files

| File | Role |
|------|------|
| `registry.py` | `SemanticRegistry`: the `products` model, two dims, one metric, no joins. The one authored artifact. |
| `tools.py` | Module-level `list_models` / `describe_model` / `run_semantic_query` delegating to the library compiler. |
| `transform.py` | Self-seeds this DP's OWN `products` base table (CREATE + INSERT), provisions the single-table `PRODUCTS_SEMANTIC` view, and writes the promised marker; its presence triggers sibling bundling. |
| `models.py` | The promised `pharma_product_marker` model (satisfies the storage output port) + the `products` schema descriptor. |
| `spec.py` | Wires the plain storage port (NO `as_view`), the transform, and the rpc/MCP output. |
| `requirements.txt` | `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`. |

## Deploy pattern: self-seed (mirrors `deployable-dp/`)

The `.transform(...)` creates and seeds this DP's OWN `products` base table
(CREATE TABLE + INSERT) and provisions a single-table `PRODUCTS_SEMANTIC` view
over it, then writes the promised marker — all in this DP's own Snowflake schema.
The storage output port is a plain `storage(...)` with NO `as_view` (the nxd
validator hard-rejects `.transform()` + `as_view()` together).

For this joinless / leaf model there is no plain-view DDL (the library requires a
join for `plain_view_ddl`); `run_semantic_query` compiles `use_view=True`
directly against the hand-authored single-table `PRODUCTS_SEMANTIC` view the
transform provisions over this DP's own `products` table.

## Local validation (no cluster)

```bash
PYTHONPATH=. \
  /Volumes/PRO-G40/projects/nxd/.claude/worktrees/t2sql-exp/examples/t2sql-poc/.venv/bin/python -c "
from registry import REGISTRY
from nxd.experimental.semantic import build_semantic_tools
from nxd.experimental.semantic.compiler import compile_selection
from nxd.experimental.semantic.dialect import SnowflakeDialect
d = SnowflakeDialect(view_name=SnowflakeDialect.default_view_name(REGISTRY))
print([t.name for t in build_semantic_tools(REGISTRY)])
print(compile_selection({'measures':['product_count'],'dimensions':['modality'],'filters':[]},
                        registry=REGISTRY, dialect=d, fqn='DB.SCH.', use_view=True))
"
```

## Wiring constraints (non-negotiable)

1. `code()` cannot extract closures → module-level tool functions in `tools.py`.
2. Sibling modules bundle only if a `.transform(...)` is declared → keep one.
3. All modules flat at the DP root → import flat (`from registry import REGISTRY`).
4. Base tables are self-seeded by the `.transform(...)` (CREATE + INSERT into
   this DP's own schema); the single-table semantic view references ONLY this
   DP's own table.
