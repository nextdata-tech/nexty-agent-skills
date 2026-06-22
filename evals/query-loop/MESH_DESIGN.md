# Pharma Mesh — Design (realistic-mesh contract, v2)

The shared contract every authoring agent implements. A synthetic biopharma mesh
(clinical-trial shaped, fully synthetic) deployed as **real semantic-layer DPs**
on the local cluster, each exposing `list_models`/`describe_model`/
`run_semantic_query` over MCP — wired as a **genuine mesh**: downstream DPs
consume upstream DPs via `.input(...)`, cross-DP relationships are declared
(`.referencing(...)`) and exposed so the query layer can resolve real cross-DP
joins, and a central **glossary DP** ties the business terms together.

## Deploy pattern: TRANSFORM-SEED (corrected)

Each DP **seeds its own base tables + creates its single-table semantic view in
the `.transform()`**, promises those tables on the output port, and deploys
green in one launch. This mirrors the proven `hcp-master` reference.

> **Correction (supersedes the v1 self-seed/provision guidance):** earlier drafts
> claimed output-port promise verification runs BEFORE the transform and forced
> seeding into `@on_provision`. That was wrong. Only **input expectations** verify
> early; output-port promises do not block a transform-seed, and downstream DPs
> don't run until their upstream triggers anyway. The `@on_provision` +
> `.provision(script())` detour also hit a platform bug (the hook registers but
> the body is never invoked → empty tables). **Seed in the transform.** No
> facade `as_view` (mutually exclusive with the required `.transform()`).

## Mesh wiring — the four real-mesh primitives (all implemented)

1. **Upstream→downstream consumption** — a downstream DP reads an upstream DP's
   output port:
   ```python
   .input("subjects", data_product_input()
       .source("/data-product/pharma-subjects-demo#/output/port/snowflake")
       .environment("demo"))
   ```
2. **Declared cross-DP FK** — an attribute references another DP's model:
   ```python
   attribute("SUBJECT_ID", int64()).referencing(
       data_product="pharma-subjects-demo", model="subjects", attribute=["SUBJECT_ID"])
   ```
3. **Registry cross-DP label + join** — the stub join target carries the owning
   DP label so the compiler marks it cross-DP and emits the join:
   ```python
   .model("subjects", grain="SUBJECT_ID", data_product="pharma-subjects-demo")
   .join(left="visits", right="site_subjects", on=(("SUBJECT_ID","SUBJECT_ID"),),
         cardinality=Cardinality.MANY_TO_ONE)
   ```
4. **Glossary DP** — a no-transform glossary DP (`.glossary("glossary.yaml")`)
   holding the shared business terms; every DP `.link(Predicate.GlossaryTerm, "…")`
   to the relevant term.

The compiler emits cross-DP JOIN SQL natively (BFS join path, fan-out-safe CTEs;
the `cross_dp` flag is diagnostic). The query skill's `semantic_relations.py`
aggregates each DP's declared relationships into one bundle for the plan validator.

## Why richer

The existing mesh has ONE crosswalk + two facts. To stress the query skills we add:
- a **second fan-out grain** off subjects (clinical **visits**) so a third chasm trap exists,
- a far **adverse-events** fact reachable only 3 hops out,
- **confusable metric pairs** within a model (so the intent gate must disambiguate),
- a **PII dimension on a non-spine model** (so cross-grain PII refusal is exercised).

## DPs + entities (grain) + role

| DP | entity (grain) | role | PII |
|---|---|---|---|
| **DP_REGISTRY** | `subjects` (subject_id) | subject spine | `subject_mrn` |
| **DP_SITES** | `site_subjects` (site_id, subject_id) | **MANY_TO_MANY crosswalk hub** | — |
| | `sites` (site_id) | site dimension | — |
| **DP_VISITS** | `visits` (visit_id) | **fact #1**: MANY visits per subject (`visit_duration_min`, `visit_count`) | — |
| **DP_LABS** | `assays` (assay_id) | **fact #2**: MANY assays per subject (`titer_sum`, confusable `titer_avg`) | — |
| **DP_RX** | `dispenses` (dispense_id) | **fact #3**: MANY dispenses per subject (`units_dispensed`, `dispense_count`); confusable `prescriber_npi` | `prescriber_npi` |
| **DP_SAFETY** | `adverse_events` (ae_id) | **far fact**: MANY AEs per subject, reachable subject→site_subjects→…; (`ae_count`, confusable `serious_ae_count` boolean flag) | — |
| **DP_PRODUCT** | `products` (product_id) | far dimension, multi-hop only | — |
| **DP_GLOSSARY** | — (glossary terms) | central business glossary (`.glossary(...)`, no transform); every DP `.link(GlossaryTerm)` to it | — |

## Deploy order (dependency chain)

Deploy in topological order so each upstream exists before its downstream's
`.input(...source)` resolves:

```
1. pharma-glossary-demo   (no deps — glossary only)
2. pharma-subjects-demo   (spine — no upstream DP input)
3. pharma-sites-demo      (.input subjects)           → crosswalk hub
4. pharma-visits-demo     (.input sites)  ┐
5. pharma-labs-demo       (.input sites)  ┤ facts: also .referencing subjects
6. pharma-rx-demo         (.input sites, .input product) 
7. pharma-product-demo    (far dim — deploy before rx, or rx references it)
8. pharma-safety-demo     (.input sites)  ┘
```

(product has no upstream; deploy it before rx since rx `.input()`s it. So real
order: glossary, subjects, sites, product, visits, labs, rx, safety.)

## Join topology (every arrow crosses a DP boundary)

```
visits  ─┐
assays  ─┤
dispenses┼─► site_subjects (MANY_TO_MANY) ─► subjects ─► (country, subject_mrn[PII])
adverse_events ─┘                          └─► sites (site dim)
dispenses ─► products (far dim, via product_id)
```

- `subjects` is the spine; `site_subjects` is the MANY_TO_MANY crosswalk.
- Each fact (`visits`/`assays`/`dispenses`/`adverse_events`) is MANY-per-subject, joined to the spine **through** the crosswalk → DISTINCT-the-crosswalk fan-out guard required.
- `products` reachable only `dispenses → products` (or multi-hop).

## The chasm traps (discriminators the test suite hammers)

1. **Two facts, one dimension** — "total titer_sum AND total units_dispensed per subject_country": pulls two MANY-per-subject facts from different DPs grouped by a third DP's dim through the crosswalk. Naive join double-counts both. (existing trap, kept)
2. **Triple fan-out** — add `visit_duration_min`: three facts at three grains off the same spine. Naive join cubes the over-count.
3. **Boolean-flag confusion** — `serious_ae_count` is a `boolean=True` CASE-sum, not a numeric SUM; `ae_count` is a plain count. Asking "serious adverse events" must pick the flag metric.
4. **Cross-grain PII refusal** — "units_dispensed by prescriber_npi" — PII dim on the RX model at dispense grain, incompatible across a cross-DP grain → the library must REFUSE (the intent gate should abstain).

## Confusable concept pairs (intent-gate stressors)

- `titer_sum` (Σ) vs `titer_avg` (mean) — both on assays; a loosely-worded "titer level" is ambiguous.
- `dispense_count` (rows) vs `units_dispensed` (Σ units) — "how much dispensed" is ambiguous.
- `ae_count` (all) vs `serious_ae_count` (flag) — "adverse events" without "serious" is ambiguous.
- `visit_count` vs `subject_count` — "how many visits" vs "how many subjects".

## Per-DP authoring spec (each agent produces ONE DP dir)

**Deploy pattern: SELF-SEED, like `deployable-dp/` — NOT facade.** (Corrected after Phase-1 review: spec validation hard-rejects `.transform()` + `as_view()` together, and rpc-tool sibling bundling (the `**/*.py` glob) only fires when a transform exists. So a facade DP can't bundle `registry.py`/`tools.py` → pod dies `ModuleNotFoundError: registry`. The two constraints are mutually exclusive; the self-seed path is the only one that both bundles siblings AND validates — verified by deploying a self-seed instance live.)

Mirror `deployable-dp/` exactly (the 4 wiring constraints are non-negotiable):
- `registry.py` — `SemanticRegistry` for that DP's entity/entities (models, dimensions w/ pii flags, metrics w/ agg + boolean flags, N:1 joins). The ONE authored artifact.
- `tools.py` — module-level `list_models`/`describe_model`/`run_semantic_query` delegating to the library; reuse `build_semantic_tools(REGISTRY)` only for request/response models + descriptions. (constraint #1: no `code()` over closures)
- `transform.py` — **self-seeds this DP's OWN base tables** (CREATE + INSERT into the DP's Snowflake schema) and provisions a **single-table** `<MODEL>_SEMANTIC` view. CRITICAL: the view DDL must reference ONLY this DP's own tables — **never** emit a view DDL that JOINs to a table living in ANOTHER DP's schema (a cross-DP join at view-creation time binds the missing object → `CREATE VIEW` fails → transform fails → DP `Failed`). Hand-author the single-table view, or make the transform a benign no-op + put the single-table view in a provision SQL.
- `models.py` — single promised marker model.
- `spec.py` — `.transform(...)` + storage output port (plain `storage(...)`, **NO `as_view`**) + rpc/MCP output (`mcp_path("/mcp")`), `INFRA_PROFILE = "ecommerce-demo"`.
- `requirements.txt` — `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`.
- Flat layout (constraint #2); matched wheel set ≥0.41.90 in the local pip registry.

Base tables: each DP self-seeds its OWN tables into its OWN schema (the template pattern). Cross-DP joins resolve at QUERY time via the live mesh, not at view-creation time. Entity names globally unique across DPs (so bare-name `Relationship.target` resolves). Stub-declare a cross-DP join target model in `registry.py` only to satisfy join-endpoint validation (siblings rx/visits/safety already do this) — but NEVER materialize a view that references it.

**MANDATORY self-check (the gap that let bad DPs pass): run `spec.validate()`** via nxd's own loader, not just `compile_selection` + `py_compile`. A DP that compiles + has 3 tools can still fail validation (facade+transform) or fail at deploy (cross-DP view DDL). Load the spec the way `nxd launch` does and assert `.validate()` raises nothing.

## Naming

DPs: `pharma-<entity>-demo` (e.g. `pharma-subjects-demo`, `pharma-assays-demo`). Keeps them grouped + distinct from the stale `semantic-smoke*`.
