# pharma-labs-demo — fact #2 (assays)

**Fact #2** of the fresh pharma mesh (`MESH_DESIGN.md` → `DP_REGISTRY`). A
deployable Nextdata OS semantic-layer data product exposing a governed
text-to-SQL layer over the `assays` model (grain `ASSAY_ID`) via **four**
auto-generated MCP tools (`list_models`, `semantic_model`, `describe_model`,
`run_semantic_query`), auto-wired by the `.semantic_tools()` spec flag (NEX-710).

## Semantic shape

- **Model:** `assays` (grain `ASSAY_ID`) — one row per lab assay; MANY assays
  per subject.
- **Dimensions:** `assay_type` (string) — ELISA / PCR / titration.
- **Metrics:** `titer_sum` — `SUM(TITER)`; `titer_avg` — `AVG(TITER)`. Both
  derive from the same `TITER` column.
- **Joins:** `assays → site_subjects` (`MANY_TO_ONE` on `SUBJECT_ID`). Only this
  first hop is declared on this DP's model; the crosswalk → spine second hop
  resolves at the mesh layer at query time, never in this DP's single-table SQL.

`titer_sum` vs `titer_avg` is a deliberate **confusable** metric pair — a
loosely-worded "titer level" is ambiguous, so the intent gate must disambiguate
total titer (sum) from mean titer (avg).

## How the semantic layer is wired (NEX-710)

The DP exposes four auto-generated MCP tools — `list_models`, `semantic_model`,
`describe_model`, `run_semantic_query` — wired by the `.semantic_tools(service=...)`
flag on the spec. There is **no** `registry.py`, **no** `tools.py`, **no**
`provision.py`, **no** `@on_provision` hook, and **no** `<MODEL>_SEMANTIC` view.

The semantic vocabulary is authored as per-field `__nxd_semantic__` annotations
on the model attributes in `models.py` (injected via the `_annotate()` NEX-704
stopgap that writes `AttributeSpec._metadata` directly). At pod boot the kernel
compiles those annotations into typed SemanticRegistry payloads and delivers one
`<root>/.nxd/semantic/<model>.json` per annotated model. The auto-generated
`run_semantic_query` reads those payloads and compiles governed SQL against the
**base tables** directly — no provisioned view required.

## Deploy pattern: SELF-SEED

The `.transform(...)` self-seeds this DP's OWN `ASSAYS` base table with
`CREATE OR REPLACE TABLE` **unquoted** (so Snowflake folds it to upper-case,
matching the compiler's unquoted base-table SQL) + `write_pandas`, and writes an
`assays_smoke_marker` row for produce-verification. The storage output port
promises every annotated model (`assays`) plus the marker via a plain
`storage(...)` — **no** `as_view` (the nxd validator hard-rejects
`.transform()` + `as_view()` together).

## Files

| File | Role |
|------|------|
| `models.py` | The real `assays` model with per-field `__nxd_semantic__` annotations (grain on `ASSAY_ID`, `assay_type` dim, the confusable `titer_sum` / `titer_avg` metric pair on `TITER`, the `SUBJECT_ID` `MANY_TO_ONE` join key into `site_subjects`) plus the `assays_smoke_marker` produce-verification model. |
| `transform.py` | Self-seeds the `ASSAYS` base table (`CREATE OR REPLACE TABLE` unquoted + `write_pandas`) and writes the marker row. |
| `spec.py` | Wires the `pharma-sites-demo` input + transform + plain storage port (NO `as_view`) + `.semantic_tools(service="mcp-api-service-k8s")`. `INFRA_PROFILE = "ecommerce-demo"`. |
| `requirements.txt` | `nxd.core`, `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`, `pyyaml>=6.0.2`. |
| `README.md` | This file. |

## Local validation (no cluster)

```bash
python3 -c "import ast; [ast.parse(open(f).read()) for f in ('models.py','transform.py','spec.py')]; print('OK')"
```

## Mesh role

`assays` is **fact #2** — MANY assays per subject, joined `MANY_TO_ONE` to the
`site_subjects` crosswalk hub (owned by `pharma-sites-demo`) via `SUBJECT_ID`.
Its `SUBJECT_ID` attribute `.referencing(...)`s the `subjects` spine in
`pharma-subjects-demo`, so the cross-DP SEMANTIC RELATIONSHIP renders in the
discover UI and resolves across the live mesh at query time. The spec declares
the genuine upstream dependency on `pharma-sites-demo`. Model and attribute
links point at the canonical glossary terms in `pharma-glossary-demo` (`assay`,
`titer`, `subject`, `site`). See `MESH_DESIGN.md` for the full registry and join
topology.
