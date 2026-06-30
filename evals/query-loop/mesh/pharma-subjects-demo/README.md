# pharma-subjects-demo — subject spine

The **subject spine** DP of the fresh pharma mesh (`MESH_DESIGN.md` → `DP_REGISTRY`).
A deployable Nextdata OS semantic-layer data product exposing a governed
text-to-SQL layer over the `subjects` model (grain `SUBJECT_ID`) via **four**
auto-generated MCP tools (`list_models`, `semantic_model`, `describe_model`,
`run_semantic_query`), auto-wired by the `.semantic_tools()` spec flag (NEX-710).

## Semantic shape

- **Model:** `subjects` (grain `SUBJECT_ID`) — the spine every mesh fact fans into.
- **Dimensions:** `subject_country` (string), `subject_mrn` (string, **PII**).
- **Metric:** `subject_count` — `COUNT_DISTINCT(SUBJECT_ID)`.
- **Joins:** none. This DP *is* the spine; the crosswalk + facts live in sibling
  DPs and resolve `subjects` by globally-unique bare name.

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

The `.transform(...)` self-seeds this DP's OWN `SUBJECTS` base table with
`CREATE OR REPLACE TABLE` **unquoted** (so Snowflake folds it to upper-case, matching
the compiler's unquoted base-table SQL) + `write_pandas`, and writes a
`subjects_smoke_marker` row for produce-verification. The storage output port
promises every annotated model (`subjects`) plus the marker via a plain
`storage(...)` — **no** `as_view` (the nxd validator hard-rejects
`.transform()` + `as_view()` together).

## Files

| File | Role |
|------|------|
| `models.py` | The real `subjects` model with per-field `__nxd_semantic__` annotations (grain + `subject_count` metric on `SUBJECT_ID`, `subject_country` dim, `subject_mrn` PII dim) plus the `subjects_smoke_marker` produce-verification model. |
| `transform.py` | Self-seeds the `SUBJECTS` base table (`CREATE OR REPLACE TABLE` unquoted + `write_pandas`) and writes the marker row. |
| `spec.py` | Wires transform + plain storage port (NO `as_view`) + `.semantic_tools(service="mcp-api-service-k8s")`. `INFRA_PROFILE = "ecommerce-demo"`. |
| `requirements.txt` | `nxd.core`, `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`, `pyyaml>=6.0.2`. |
| `README.md` | This file. |

## Local validation (no cluster)

```bash
python3 -c "import ast; [ast.parse(open(f).read()) for f in ('models.py','transform.py','spec.py')]; print('OK')"
```

## Mesh role

`subjects` is the spine: it has no outgoing cross-DP reference. Its attributes
link to glossary terms in `pharma-glossary-demo`. The crosswalk and downstream
fact DPs resolve `subjects` by its globally-unique bare model name and carry the
cross-DP SEMANTIC RELATIONSHIP back to this spine. See `MESH_DESIGN.md` for the
full registry and join topology.
