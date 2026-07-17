# pharma-visits-demo — clinical-visits fact

**Fact #1** of the fresh pharma mesh (`MESH_DESIGN.md` → `DP_VISITS`). A
deployable Nextdata OS semantic-layer data product exposing a governed
text-to-SQL layer over the `visits` model (grain `VISIT_ID`, MANY visits per
subject) via **four** auto-generated MCP tools (`list_models`, `semantic_model`,
`describe_model`, `run_semantic_query`), auto-wired by the `.semantic_tools()`
spec flag (NEX-710).

## Semantic shape

- **Model:** `visits` (grain `VISIT_ID`) — one row per clinical visit, MANY
  visits per subject.
- **Dimensions:** `visit_type` (string — screening / baseline / follow-up).
- **Metrics:** `visit_count` = `COUNT_DISTINCT(VISIT_ID)`; `visit_duration_min`
  = `SUM(DURATION_MIN)`.
- **Joins:** `visits` → `site_subjects` **MANY_TO_ONE** on `SUBJECT_ID` — this
  DP's OWN first hop into the crosswalk hub (owned by `pharma-sites-demo`). The
  further hop (`site_subjects` → `subjects`) and the foreign spine dimensions
  (`subject_country`, `subject_mrn`) are NOT redeclared here; the mesh resolves
  that edge at query time.

**Confusable pair (cross-grain):** `visit_count` (how many visits, this model)
vs `subject_count` (how many subjects, owned by `pharma-subjects-demo`'s
`subjects` model). "How many visits" must resolve to `visit_count` here, NOT
`subject_count`.

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

The `.transform(...)` self-seeds this DP's OWN `VISITS` base table with
`CREATE OR REPLACE TABLE` **unquoted** (so Snowflake folds it to upper-case, matching
the compiler's unquoted base-table SQL) + `write_pandas`, and writes a
`visits_smoke_marker` row for produce-verification. The storage output port
promises every annotated model (`visits`) plus the marker via a plain
`storage(...)` — **no** `as_view` (the nxd validator hard-rejects
`.transform()` + `as_view()` together).

## Files

| File | Role |
|------|------|
| `models.py` | The real `visits` model with per-field `__nxd_semantic__` annotations (grain + `visit_count` metric on `VISIT_ID`, `visit_duration_min` metric on `DURATION_MIN`, `visit_type` dim, N:1 join on `SUBJECT_ID`) plus the `visits_smoke_marker` produce-verification model. |
| `transform.py` | Self-seeds the `VISITS` base table (`CREATE OR REPLACE TABLE` unquoted + `write_pandas`) and writes the marker row. |
| `spec.py` | Wires the upstream `pharma-sites-demo` input + transform + plain storage port (NO `as_view`) + `.semantic_tools(service="mcp-api-service-k8s")`. `INFRA_PROFILE = "ecommerce-demo"`. |
| `requirements.txt` | `nxd.core`, `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`, `pyyaml>=6.0.2`. |
| `README.md` | This file. |

## Local validation (no cluster)

```bash
python3 -c "import ast; [ast.parse(open(f).read()) for f in ('models.py','transform.py','spec.py')]; print('OK')"
```

## Mesh role

`visits` is fact #1: it carries an outgoing cross-DP reference on `SUBJECT_ID`
into the crosswalk hub `site_subjects` (owned by `pharma-sites-demo`), declaring
only its OWN first join hop (MANY_TO_ONE). The mesh resolves the further hop into
the `subjects` spine and the foreign spine dimensions at query time. The spec
consumes the upstream `pharma-sites-demo` output port as a real input, wiring the
upstream→downstream dependency. Attributes link to glossary terms in
`pharma-glossary-demo` (`visit`, `subject`). See `MESH_DESIGN.md` for the full
registry and join topology.
