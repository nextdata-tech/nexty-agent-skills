# pharma-safety-demo — far adverse-events fact

The **far adverse-events fact** DP of the fresh pharma mesh (`MESH_DESIGN.md` → `DP_REGISTRY`).
A deployable Nextdata OS semantic-layer data product exposing a governed
text-to-SQL layer over the `adverse_events` model (grain `AE_ID`) via **four**
auto-generated MCP tools (`list_models`, `semantic_model`, `describe_model`,
`run_semantic_query`), auto-wired by the `.semantic_tools()` spec flag (NEX-710).

## Semantic shape

- **Model:** `adverse_events` (grain `AE_ID`) — one row per adverse event; MANY
  adverse events per subject.
- **Dimensions:** `ae_term` (string — MedDRA-style adverse-event term).
- **Metrics:** `ae_count` — `COUNT_DISTINCT(AE_ID)` (so `AE_ID` carries BOTH grain
  and metric roles); `serious_ae_count` — a **CASE-sum over the `IS_SERIOUS`
  boolean flag** (`boolean: true` — NOT a numeric SUM of a numeric column).
- **Joins:** `MANY_TO_ONE` → `site_subjects` on `SUBJECT_ID` (the crosswalk hub
  owned by sibling `pharma-sites-demo`). The foreign model is NOT declared here;
  the join resolves at the mesh layer by globally-unique bare name.

`ae_count` vs `serious_ae_count` is a **confusable pair** (intent-gate stressor):
a loosely-worded "adverse events" must pick `ae_count`; "serious adverse events"
must pick `serious_ae_count`. The latter counts rows where `IS_SERIOUS` is true
via a CASE-sum, NOT a numeric SUM.

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

The `.transform(...)` self-seeds this DP's OWN `ADVERSE_EVENTS` base table with
`CREATE OR REPLACE TABLE` **unquoted** (so Snowflake folds it to upper-case, matching
the compiler's unquoted base-table SQL) + `write_pandas`, and writes an
`adverse_events_smoke_marker` row for produce-verification. The storage output port
promises every annotated model (`adverse_events`) plus the marker via a plain
`storage(...)` — **no** `as_view` (the nxd validator hard-rejects
`.transform()` + `as_view()` together).

## Files

| File | Role |
|------|------|
| `models.py` | The real `adverse_events` model with per-field `__nxd_semantic__` annotations (grain + `ae_count` metric on `AE_ID`, `ae_term` dim, N:1 join + cross-DP FK on `SUBJECT_ID`, `serious_ae_count` boolean CASE-sum on `IS_SERIOUS`) plus the `adverse_events_smoke_marker` produce-verification model. |
| `transform.py` | Self-seeds the `ADVERSE_EVENTS` base table (`CREATE OR REPLACE TABLE` unquoted + `write_pandas`) and writes the marker row. |
| `spec.py` | Wires transform + plain storage port (NO `as_view`) + `.semantic_tools(service="mcp-api-service-k8s")`. `INFRA_PROFILE = "ecommerce-demo"`. |
| `requirements.txt` | `nxd.core`, `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`, `pyyaml>=6.0.2`. |
| `README.md` | This file. |

## Local validation (no cluster)

```bash
python3 -c "import ast; [ast.parse(open(f).read()) for f in ('models.py','transform.py','spec.py')]; print('OK')"
```

## Mesh role

`adverse_events` is the far fact: it fans MANY_TO_ONE into `site_subjects` (the
crosswalk hub owned by `pharma-sites-demo`) on `SUBJECT_ID`, and carries a cross-DP
SEMANTIC RELATIONSHIP FK back to `subjects` (owned by `pharma-subjects-demo`).
spec.py consumes `pharma-sites-demo`'s storage port as a real mesh input, so the
upstream→downstream dependency is declared and the cross-DP join resolves at query
time via the live mesh. Its model and attributes link to glossary terms
(`adverse_event`, `subject`, `serious_ae`) in `pharma-glossary-demo`. See
`MESH_DESIGN.md` for the full registry and join topology.
