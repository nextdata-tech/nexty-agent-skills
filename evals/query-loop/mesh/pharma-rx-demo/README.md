# pharma-rx-demo — dispense fact (DP_RX)

The **dispense fact** DP of the fresh pharma mesh (`MESH_DESIGN.md` → `DP_REGISTRY`).
A deployable Nextdata OS semantic-layer data product exposing a governed
text-to-SQL layer over pharmacy **dispenses** (`dispenses` model, grain
`DISPENSE_ID`) via **four** auto-generated MCP tools (`list_models`,
`semantic_model`, `describe_model`, `run_semantic_query`), auto-wired by the
`.semantic_tools()` spec flag (NEX-710).

## Semantic shape

- **Model:** `dispenses` (grain `DISPENSE_ID`) — one row per medication dispense;
  MANY dispenses per subject.
- **Dimensions:** `dispense_channel` (string — retail / mail-order / specialty),
  `prescriber_npi` (string, **PII** — prescriber National Provider Identifier).
- **Metrics (confusable pair):**
  - `dispense_count` — `COUNT_DISTINCT(DISPENSE_ID)` — *how many* dispenses occurred.
  - `units_dispensed` — `SUM(UNITS)` — *how much* medication was dispensed.
  - These are easily confused; keep "number of dispenses" vs "total units" distinct.
- **Joins (N:1, MANY side is `dispenses`):**
  - `dispenses ─► site_subjects` on `SUBJECT_ID` (crosswalk hub → subject spine, DP_SITES).
  - `dispenses ─► products` on `PRODUCT_ID` (far dimension, DP_PRODUCT).

  The grain column `DISPENSE_ID` carries BOTH a grain role and the
  `dispense_count` metric role. Entity/model names are globally unique across the
  mesh so bare-name joins resolve against the other DPs' registries at cross-DP
  plan time.

## How the semantic layer is wired (NEX-710)

The DP exposes four auto-generated MCP tools — `list_models`, `semantic_model`,
`describe_model`, `run_semantic_query` — wired by the `.semantic_tools(service=...)`
flag on the spec. There is **no** `registry.py`, **no** `tools.py`, **no**
`provision.py`, **no** `@on_provision` hook, and **no** `<MODEL>_SEMANTIC` view.

The semantic vocabulary is authored as per-field `__nxd_semantic__` annotations
on the `dispenses` attributes in `models.py` (injected via the `_annotate()`
NEX-704 stopgap that writes `AttributeSpec._metadata` directly). At pod boot the
kernel compiles those annotations into typed SemanticRegistry payloads and
delivers one `<root>/.nxd/semantic/<model>.json` per annotated model. The
auto-generated `run_semantic_query` reads those payloads and compiles governed
SQL against the **base tables** directly — no provisioned view required.

## Deploy pattern: SELF-SEED

The `.transform(...)` self-seeds this DP's OWN `DISPENSES` base table with
`CREATE OR REPLACE TABLE` **unquoted** (so Snowflake folds it to upper-case,
matching the compiler's unquoted base-table SQL) + `write_pandas`, and writes a
`dispenses_smoke_marker` row for produce-verification. The storage output port
promises every annotated model (`dispenses`) plus the marker via a plain
`storage(...)` — **no** `as_view` (the nxd validator hard-rejects
`.transform()` + `as_view()` together).

## Files

| File | Role |
|------|------|
| `models.py` | The real `dispenses` model with per-field `__nxd_semantic__` annotations (grain + `dispense_count` metric on `DISPENSE_ID`, `units_dispensed` metric on `UNITS`, `dispense_channel` dim, `prescriber_npi` PII dim, two N:1 cross-DP join blobs on `SUBJECT_ID`/`PRODUCT_ID`) plus the `dispenses_smoke_marker` produce-verification model. |
| `transform.py` | Self-seeds the `DISPENSES` base table (`CREATE OR REPLACE TABLE` unquoted + `write_pandas`) and writes the marker row. |
| `spec.py` | Wires upstream mesh inputs (`pharma-sites-demo`, `pharma-product-demo`) + transform + plain storage port (NO `as_view`) + `.semantic_tools(service="mcp-api-service-k8s")`. `INFRA_PROFILE = "ecommerce-demo"`. |
| `requirements.txt` | `nxd.core`, `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`, `pyyaml>=6.0.2`. |
| `README.md` | This file. |

## Local validation (no cluster)

```bash
python3 -c "import ast; [ast.parse(open(f).read()) for f in ('models.py','transform.py','spec.py')]; print('OK')"
```

## Mesh role

`dispenses` is a MANY-side fact: it carries outgoing cross-DP references on its
foreign keys — `SUBJECT_ID → pharma-subjects-demo/subjects` (via the
`site_subjects` crosswalk hub) and `PRODUCT_ID → pharma-product-demo/products`.
The `site_subjects → subjects` second hop is published by `pharma-sites-demo`.
Its model and key attributes link to glossary terms in `pharma-glossary-demo`
(dispense, subject, product, prescriber, site), and the cross-DP SEMANTIC
RELATIONSHIP surfaces in the discover UI. See `MESH_DESIGN.md` for the full
registry and join topology.
