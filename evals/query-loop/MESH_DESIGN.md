# Fresh Pharma Mesh — Design (Phase 1 contract)

The shared contract every Phase-1 authoring agent implements. A richer synthetic
biopharma mesh (argenx-*shaped*, nothing argenx-specific) deployed as **real
semantic-layer DPs** on the local cluster, each exposing
`list_models`/`describe_model`/`run_semantic_query` over MCP.

Built from the proven `examples/t2sql-poc/deployable-dp/` template — the
**self-seed** deploy pattern (a `.transform()` seeds the DP's own tables + a
single-table semantic view; NO facade `as_view`). Richer than the existing 5-DP
`pharma_mesh`: **7 DPs**, deeper multi-hop chains, more chasm traps, more
confusable concepts.

> **Phase-1 correction:** an earlier draft of this design specified the *facade*
> (`as_view`) pattern. The nxd validator forbids `as_view` + `.transform()`
> together, and rpc-tool sibling bundling REQUIRES a transform — so facade DPs
> can't ship the `registry.py`/`tools.py` siblings the MCP tools import. The
> self-seed template is the only deployable shape. See the per-DP spec below + the
> audit log.

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

**Deploy pattern: SELF-SEED, like `deployable-dp/` — NOT facade.** (Corrected after Phase-1 review: the nxd validator `_validate_facade_outputs` HARD-REJECTS `.transform()` + `as_view()` together — `_spec.py:5309-5314` — and the rpc-tool sibling bundling (`**/*.py` glob) only fires when an `executor_spec`/transform exists (`fs/_fs_spec.py:29` returns early `if not self.executor_spec`). So a facade DP can't bundle `registry.py`/`tools.py` → pod dies `ModuleNotFoundError: registry`. The two constraints are mutually exclusive; the template's self-seed path is the only one that both bundles siblings AND validates. `hcp-master-demo` is a deployed self-seed instance — proof.)

Mirror `deployable-dp/` exactly (the 4 wiring constraints are non-negotiable):
- `registry.py` — `SemanticRegistry` for that DP's entity/entities (models, dimensions w/ pii flags, metrics w/ agg + boolean flags, N:1 joins). The ONE authored artifact.
- `tools.py` — module-level `list_models`/`describe_model`/`run_semantic_query` delegating to the library; reuse `build_semantic_tools(REGISTRY)` only for request/response models + descriptions. (constraint #1: no `code()` over closures)
- `transform.py` — **self-seeds this DP's OWN base tables** (CREATE + INSERT into the DP's Snowflake schema) and provisions a **single-table** `<MODEL>_SEMANTIC` view. CRITICAL: the view DDL must reference ONLY this DP's own tables — **never** call the compiler's `native_semantic_view_ddl`/`plain_view_ddl` when the registry has a cross-DP join (those emit a JOIN to the crosswalk table that lives in ANOTHER DP's schema → `CREATE VIEW` binds the missing object → transform fails → DP `Failed`). This was the pharma-labs-demo break. Hand-author the single-table view, or make the transform a benign no-op + put the single-table view in a provision SQL.
- `models.py` — single promised marker model.
- `spec.py` — `.transform(...)` + storage output port (plain `storage(...)`, **NO `as_view`**) + rpc/MCP output (`mcp_path("/mcp")`), `INFRA_PROFILE = "ecommerce-demo"`.
- `requirements.txt` — `nxd.data_product[spec]`, `nxd.drivers[rpc]`, `snowflake-connector-python[pandas]`, `pandas`.
- Flat layout (constraint #2); matched wheel set ≥0.41.90 in the local pip registry.

Base tables: each DP self-seeds its OWN tables into its OWN schema (the template pattern). Cross-DP joins resolve at QUERY time via the live mesh, not at view-creation time. Entity names globally unique across DPs (so bare-name `Relationship.target` resolves). Stub-declare a cross-DP join target model in `registry.py` only to satisfy join-endpoint validation (siblings rx/visits/safety already do this) — but NEVER materialize a view that references it.

**MANDATORY self-check (the gap that let bad DPs pass): run `spec.validate()`** via nxd's own loader, not just `compile_selection` + `py_compile`. A DP that compiles + has 3 tools can still fail validation (facade+transform) or fail at deploy (cross-DP view DDL). Load the spec the way `nxd launch` does and assert `.validate()` raises nothing.

## Naming

DPs: `pharma-<entity>-demo` (e.g. `pharma-subjects-demo`, `pharma-assays-demo`). Keeps them grouped + distinct from the stale `semantic-smoke*`.
