# pharma-sites-demo — MANY_TO_MANY crosswalk hub

The **MANY_TO_MANY crosswalk hub** DP of the fresh pharma mesh (`MESH_DESIGN.md` →
`DP_SITES`). A deployable Nextdata OS semantic-layer data product exposing a
governed text-to-SQL layer over the `sites` dimension and the `site_subjects`
crosswalk via **four** auto-generated MCP tools (`list_models`, `semantic_model`,
`describe_model`, `run_semantic_query`), auto-wired by the `.semantic_tools()`
spec flag (NEX-710).

## Semantic shape

- **Models:**
  - `sites` (grain `SITE_ID`) — the site dimension.
  - `site_subjects` (grain `SITE_ID, SUBJECT_ID`) — the MANY_TO_MANY fan-out
    crosswalk hub, one row per (site, subject) enrollment.
- **Dimensions:** `site_region` (string, on `sites`).
- **Metric:** `site_count` — `COUNT_DISTINCT(SITE_ID)` (on `sites`).
- **Joins:** both grain columns of `site_subjects` carry a `MANY_TO_ONE` join
  blob — `SITE_ID` → this DP's own `sites` (`SITE_ID`), `SUBJECT_ID` → the
  cross-DP subject spine `subjects` (`SUBJECT_ID`, owned by
  `pharma-subjects-demo`). Foreign models/dimensions are **not** redeclared here;
  the mesh resolves them at query time by globally-unique bare model name.

> Confusable-metric note: this DP owns exactly one metric, `site_count`
> (distinct sites). The subject spine's `subject_count` and any per-fact metrics
> live on their owning DPs — don't conflate them; `site_count` answers
> "how many distinct sites", never "how many subjects".

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

The `.transform(...)` self-seeds this DP's OWN `SITES` and `SITE_SUBJECTS` base
tables with `CREATE OR REPLACE TABLE` **unquoted** (so Snowflake folds them to
upper-case, matching the compiler's unquoted base-table SQL) + `write_pandas`,
and writes a `sites_smoke_marker` row for produce-verification. The storage
output port promises every annotated model (`sites`, `site_subjects`) plus the
marker via a plain `storage(...)` — **no** `as_view` (the nxd validator
hard-rejects `.transform()` + `as_view()` together).

## Files

| File | Role |
|------|------|
| `models.py` | The real `sites` model (grain + `site_count` metric on `SITE_ID`, `site_region` dim) and `site_subjects` crosswalk (both grain columns carry FK lineage + `MANY_TO_ONE` join blobs), all per-field `__nxd_semantic__` annotated, plus the `sites_smoke_marker` produce-verification model. |
| `transform.py` | Self-seeds the `SITES` + `SITE_SUBJECTS` base tables (`CREATE OR REPLACE TABLE` unquoted + `write_pandas`) and writes the marker row. |
| `spec.py` | Declares the upstream `.input(...)` on the subject spine, wires transform + plain storage port (NO `as_view`) + `.semantic_tools(service="mcp-api-service-k8s")`. `INFRA_PROFILE = "ecommerce-demo"`. |
| `requirements.txt` | `nxd.core`, `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`, `pyyaml>=6.0.2`. |
| `README.md` | This file. |

## Local validation (no cluster)

```bash
python3 -c "import ast; [ast.parse(open(f).read()) for f in ('models.py','transform.py','spec.py')]; print('OK')"
```

## Mesh role

`pharma-sites-demo` is the crosswalk hub: it consumes the subject spine upstream
(declared via `.input("pharma-subjects-demo", ...)` on its `snowflake` output
port) and fans MANY_TO_MANY between the subject spine and the site dimension.
The cross-DP edge to `subjects` is published by the `join` blob on
`site_subjects.SUBJECT_ID` — not by redeclaring the foreign model. Downstream
fact DPs reach `subjects` through this crosswalk by globally-unique bare model
name. The `sites` dimension links to the governed `site` glossary term, and the
crosswalk links to both `site` and `subject` terms in `pharma-glossary-demo`.
See `MESH_DESIGN.md` for the full registry and join topology.
