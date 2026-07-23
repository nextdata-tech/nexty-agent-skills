# Skill benchmark ledger

Append-only history of measured skill changes: for every skill improvement,
the before/after eval verdicts and efficiency metrics (turns, tool calls,
tokens, cost) that justified shipping it. Entries are appended by
`evals/benchmark_record.py` from `run.py --report` JSONs; the matching compact
reports live in `records/`. Newest entries at the bottom.

Reading a row: the judge verdict (checks passed) is the regression gate;
turns/tool_calls/tokens are the efficiency trend. Single-run metric deltas
under ~20% are noise — see "Benchmarking a skill change" in `evals/README.md`.

## 2026-07-06 — nxd-setup: sandboxed-shell headless device-flow branch (plugin v0.8.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.7.0 | current_pack | nxd-setup-headless-auth | FAIL | 3/8 | 4 | 2 | 8120 | 0.29 | sonnet |
| after-v0.8.0 | no_skills | nxd-setup-headless-auth | FAIL | 4/8 | 7 | 6 | 19724 | 0.73 | sonnet |
| after-v0.8.0 | current_pack | nxd-setup-headless-auth | PASS | 8/8 | 1 | 4 | 54 | 0.45 | sonnet |

Notes: Fix from a Cowork session debrief: interactive 'nxd login' cannot survive a per-call sandbox process tree. v0.8.0 adds a Step-4 sandboxed-shell branch + reference/headless-device-flow.md (manual curl device flow, pkce_verifier round-trip, hand-written tokens.json, PAT switch). The v0.7.0 skill scored below the no-skill baseline because it steered the agent back to re-running 'nxd login'. The no_skills row (from the after-report batch) is the lift baseline. Scenario is new in the same PR; before-run used a worktree of main with the scenario copied in.

Record: [`records/2026-07-06-nxd-setup-sandboxed-shell-headless-device-flow-branch.json`](records/2026-07-06-nxd-setup-sandboxed-shell-headless-device-flow-branch.json)

## 2026-07-13 — nxd-data-product-query: platform-routed cross-dp joins replace client-side compiler (plugin v0.9.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.8.1 | current_pack | pharma-mesh-query-loop | PASS | 12/12 | 41 | 39 | 15776 | 1.47 | sonnet |
| after-v0.9.0-run2 | current_pack | pharma-mesh-query-loop | FAIL | 11/12 | 47 | 45 | 18747 | 1.84 | sonnet |
| after-v0.9.0-run3 | current_pack | pharma-mesh-query-loop | PASS | 12/12 | 35 | 33 | 14553 | 1.41 | sonnet |

Notes: Cross-DP queries now route through the platform's query system DP (server-side harvest/merge/gate/join); strict mode and the client-side compiler are removed. Scenario prompt/checks modernized off the strict-mode framing in the same PR (numeric fan-out discriminators). run2's single q6 miss (confusable dispensed metric) did not reproduce in run3 — single-run nondeterminism, not a regression; run1 against the stale strict-mode prompt was discarded.

Record: [`records/2026-07-13-nxd-data-product-query-platform-routed-cross-dp-joins-replac.json`](records/2026-07-13-nxd-data-product-query-platform-routed-cross-dp-joins-replac.json)

## 2026-07-13 — nxd-data-product-query: cross-dp mesh gateway scenario (new) (plugin v0.9.1)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| after-v0.9.1 | current_pack | pharma-cross-dp-mesh-query | PASS | 12/12 | 40 | 38 | 19733 | 1.63 | sonnet |

Notes: New scenario pharma-cross-dp-mesh-query: a merged multi-DP semantic mesh behind one gateway (subjects spine, sites+crosswalk, labs/rx facts, product far-dim) with numeric fan-out discriminators (chasm US titer 300 / units 90; crosswalk NA 300 vs naive 450), confusable metrics, cross-boundary PII masking, and an absent safety member as an entitlement probe. Single after-run: the scenario is new in this PR, so there is no before variant of the skill to compare. First run was discarded as a harness defect, not a skill signal: the host had a live nxd session and mesh discovery hijacked the cell to the live mesh (fixed in the same PR by isolating NXD_HOME per MCP cell).

Record: [`records/2026-07-13-nxd-data-product-query-cross-dp-mesh-gateway-scenario-new.json`](records/2026-07-13-nxd-data-product-query-cross-dp-mesh-gateway-scenario-new.json)

## 2026-07-16 — nxd-semantic-data-product: infer semantic model from a live source + questions (new scenario) (plugin v0.9.1)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| after-v0.9.1 | current_pack | generate-semantic-layer-from-live-source-and-questions | FAIL | 18/19 | 18 | 16 | 13235 | 0.81 | sonnet |
| after-v0.9.1 | no_skills | generate-semantic-layer-from-live-source-and-questions | FAIL | 15/19 | 20 | 19 | 13839 | 0.81 | sonnet |
| after-deps-fix | current_pack | generate-semantic-layer-from-live-source-and-questions | FAIL | 15/19 | 15 | 13 | 13135 | 0.73 | sonnet |
| after-completeness-fix-run1 | current_pack | generate-semantic-layer-from-live-source-and-questions | FAIL | 15/19 | 12 | 10 | 8649 | 0.54 | sonnet |
| after-completeness-fix-run2 | current_pack | generate-semantic-layer-from-live-source-and-questions | FAIL | 15/19 | 17 | 15 | 12551 | 0.77 | sonnet |
| after-completeness-fix-run3 | current_pack | generate-semantic-layer-from-live-source-and-questions | FAIL | 15/19 | 15 | 13 | 10695 | 0.69 | sonnet |

Notes: New scenario generate-semantic-layer-from-live-source-and-questions: no schema document is given — the agent must materialize the landed DuckDB sample, profile both tables into schema.json, and INFER grains/dimensions/metrics/joins/PII from that profile plus four stakeholder questions, then prove them answerable via the shipped acceptance test. The scenario is new in this PR, so there is no before variant of the skill; lift is current_pack vs the equally-informed no_skills baseline. current_pack scored 18/19 vs no_skills 15/19: the baseline authored a passing models.py but never produced spec.py, transform.py, or a dependency manifest (checks 15/16/17/19), while the skill produced the full data product and missed only dependencies-present. No runs were discarded — both cells ran clean with no harness defect (no live-session hijack, no setup crash, no auth/timeout error). Plugin v0.9.1. The current_pack passing acceptance run printed MODELS_SHA256: 8b58031b7087824ca9178e09e1b41dd06bb91e9fa58971b170f808b2576b4004.

The `after-deps-fix` row verifies commit 9af1bf0, which promoted requirements.txt from a buried footnote to an explicit required Step 5 with the pinned 5-dep list. dependencies-present did NOT flip to pass — it still fails, and this re-run regressed further upstream than the prior 18/19: current_pack scored 15/19. The agent authored and validated an excellent models.py (passing the acceptance test, MODELS_SHA256 ea9783f524a0d1cc92254df7d1ac697d148e87de35a7b918d834cedd0f8acf76) but stopped there, never authoring spec.py, transform.py, or requirements.txt — so semantic-tools-flag-used, models-promised, transform-seeds-profiled-tables, and dependencies-present all failed. Not discarded: the cell ran clean (ok=true, no error, no live-session hijack, no setup crash, no auth/timeout). The requirements.txt promotion could not be confirmed as flipping dependencies-present because the agent never reached the packaging phase this pass — a signal of run-to-run nondeterminism in whether the agent completes full data-product packaging, not merely the dependency footnote.

The three `after-completeness-fix-run1/2/3` rows measure the run-to-run distribution after the completeness fix (commit 0c98c2a: a workflow banner stating the DP is FOUR files and a validated models.py is a milestone not the finish line, plus a Step 7 completeness check listing all required files). Result across 3 fresh, uncached runs: 0 PASS, 3 FAIL 15/19 — the agent stopped after models.py in ALL THREE runs. Every failing run has the same signature: it profiles the source, authors and validates a semantically correct models.py that passes the acceptance test (MODELS_SHA256 5cf94f60… run1, 4e147e09… run2, 1697839e… run3), then stops — never authoring spec.py, transform.py, or requirements.txt — so semantic-tools-flag-used, models-promised, transform-seeds-profiled-tables, and dependencies-present all fail. dependencies-present therefore stayed FAIL in all three, because no run reached the packaging phase to author a dependency file. The completeness fix did NOT reduce the stop-after-models regression in this sample: 3 of 3 runs stopped early, worse than the prior single-shot samples (18/19 after-v0.9.1, 15/19 after-deps-fix). The distribution confirms the outcome remains nondeterministic and the agent still frequently treats a validated models.py as the finish line despite the explicit four-file banner and Step 7 checklist. No runs discarded — all three cells ran clean (ok=true, no error, no live-session hijack, no setup crash, no auth/timeout).

Record: [`records/2026-07-16-nxd-semantic-data-product-infer-semantic-model-from-a-live-s.json`](records/2026-07-16-nxd-semantic-data-product-infer-semantic-model-from-a-live-s.json)

## 2026-07-17 — nxd-pocket-loop: graded serve-query-refine e2e (plugin v0.9.1)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| current_pack | current_pack | pocket-loop-serve-query-refine | PASS | 7/7 | 117 | 114 | 93775 | 12.15 | sonnet |

Notes: New scenario pocket-loop-serve-query-refine: whole local loop (infer, generate, serve, describe, governed query, refine) end to end against the desktop supervisor. First graded run, 7/7.

Record: [`records/2026-07-17-nxd-pocket-loop-graded-serve-query-refine-e2e.json`](records/2026-07-17-nxd-pocket-loop-graded-serve-query-refine-e2e.json)

## 2026-07-20 — nxd-generate-dp: desktop semantic closure and public authoring (plugin v0.11.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.10.0 | current_pack | generate-runnable-dp-from-intent | PASS | 14/14 | 22 | 20 | 9350 | 0.87 | sonnet |
| after-v0.11.0 | current_pack | generate-runnable-dp-from-intent | PASS | 9/9 | 16 | 14 | 6775 | 0.52 | sonnet |

Notes: Replaces the obsolete hand-authored local closure topology and private semantic authoring with the desktop supervisor's Python-only public DSL closure, parsed wiring checks, validated base-key tuples, and exact semantic-view metric roles.

Record: [`records/2026-07-20-nxd-generate-dp-desktop-semantic-closure-and-public-authorin.json`](records/2026-07-20-nxd-generate-dp-desktop-semantic-closure-and-public-authorin.json)

## 2026-07-21 — nxd-generate-dp + nxd-pocket-loop: multi-connector-type sources (file/database/API), labeled multi-source naming, structured API auth (plugin v0.12.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.11.0 | current_pack | generate-runnable-dp-from-intent | PASS | 9/9 | 19 | 17 | 6970 | 0.69 | sonnet |
| after-v0.12.0 | current_pack | generate-runnable-dp-from-intent | PASS | 9/9 | 17 | 15 | 7575 | 0.61 | sonnet |

Notes: Direct upgrade from 0.11.0 to 0.12.0 (renumbered from an intermediate 0.13.0/0.13.1/0.13.2 sequence to resolve a version-bump collision with PR #87, which also bumps 0.11.0 -> 0.12.0 and rebases onto this). Net effect of the whole PR: added file/database/REST-API connector types as siblings to the proven CSV closure in nxd-generate-dp (reference/file-source.md, database-source.md, api-source.md), taught nxd-pocket-loop to gather/route them, added an opt-in labeled multi-source naming scheme for 2+ sources of the same or mixed connector types (reference/multi-source.md), fixed the infra-profile.yaml credential-attribute shape (name->key, public:false) against the supervisor's real KeyValuePairWithPublic schema, and replaced the api-source connector's single opaque auth value with structured auth_type + per-type flat fields assembled into dlt's structured auth dict in the transform. The single-CSV-source default path (csv-source, csv_source, csv-source-path) is untouched throughout -- this eval only exercises that unchanged path; the new connector types and the auth_type dispatch have no scenario coverage yet (real follow-up work). pocket-loop-serve-query-refine remains blocked in this sandbox (missing nxd-desktop-supervisor binary).

Record: [`records/2026-07-21-nxd-generate-dp-nxd-pocket-loop-multi-connector-type-sources.json`](records/2026-07-21-nxd-generate-dp-nxd-pocket-loop-multi-connector-type-sources.json)

## 2026-07-21 — nxd-generate-dp / nxd-pocket-loop: derivation rulings materialize; omission-test routing (plugin v0.12.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before | current_pack | derive-models-from-questions | ERROR | — | — | — | — | — | — |
| after | current_pack | derive-models-from-questions | ERROR | — | — | — | — | — | — |

Notes: the harness cannot run this scenario in-sandbox — the same desktop-supervisor
blocker recorded against the sibling rows above. Logged ERROR rather than omitted so the
gap is visible.

Evidence was gathered instead by running isolated agents (sonnet, clean working
directory, no repo context) against the installed skills and grading with the
scenario's own deterministic checker plus withheld ground truth. Four runs:

- **Control** — a source where every question is answerable by a metric over an
  existing column. Zero derived models, correct answers. The new derivation
  guidance does not induce over-derivation.
- **Finance** — refunds, internal transfers, three currencies, no category column.
  All four currency/category totals correct to the cent against withheld truth.
- **Negative fixture** — the finance closure with the sign stripped from amounts, so
  refunds stop netting. The mandatory Tier-2 signed-measure reconciliation raised at
  build time before any data landed: `classified_spend EUR total 75614.33 != source
  -70284.47`. With that assert removed the closure builds and prints SELF-CHECK OK,
  and only the scenario's numeric gate catches it (2 failed). Defence in depth
  demonstrated on a real defect.
- **Realistic-messy** — 16 raw vendor descriptions over 7 real vendors, 9 duplicate
  transaction ids from a re-export, partial refunds, two date formats in one column,
  and an fx_rate column present but empty on every row. A naive closure lands
  12,128.61 from correct. The agent deduped correctly, resolved the primary-key
  conflict (no key on the base model, key on the derived dedupe), inferred DD/MM/YYYY
  from 23 unambiguous rows, and refused to invent an FX rate — reporting per-currency
  and naming the cost. All totals correct to the cent.

Not yet covered: expansion/collapse derivation shapes (only enrichment and removal
were exercised), the FX-applied path end-to-end, and chained derivations.

## 2026-07-23 — nxd-generate-dp + nxd-pocket-loop: policy read-back gate before materialization (plugin v0.16.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.15.2-run1 | current_pack | coauthor-supplied-rubric | FAIL | 10/11 | 5 | 4 | 5182 | 0.27 | sonnet |
| before-v0.15.2-run2 | current_pack | coauthor-supplied-rubric | FAIL | 10/11 | 7 | 5 | 6659 | 0.39 | sonnet |
| after-v0.16.0-run1 | current_pack | coauthor-supplied-rubric | FAIL | 9/11 | 6 | 4 | 5671 | 0.37 | sonnet |
| after-v0.16.0-run2 | current_pack | coauthor-supplied-rubric | FAIL | 10/11 | 6 | 4 | 5158 | 0.34 | sonnet |

Notes: New scenario coauthor-supplied-rubric: a supplied rubric defining only the 5 and the 1 on all four criteria, verdict names with no thresholds, an unknown gate, and provenance-sensitive evidence. Baseline runs use v0.15.2 skills from origin/main with the scenario and run.py copied into a worktree. Two runs per arm because single-run deltas under ~20% are noise. The nine ordering and co-authoring checks pass 4/4 in BOTH arms: the read-back was already reachable via derivation-plan.md whenever the agent happened to load that file, so on the READ-BACK axis this scenario does not separate the versions. It DOES separate them on ROUTING, which was initially assumed untestable and is not: --plugin-dir registers skills for model-driven selection, the same mechanism Desktop uses, so the transcript records which skill the model chose first from a free choice between both. Across 9 runs the first skill loaded was: before v0.15.2 (n=4) none 1, nxd-generate-dp 1, nxd-pocket-loop 2 - i.e. 2/4 failed to reach the orchestrator first; after v0.16.0 (n=5) nxd-pocket-loop 5/5. That reproduces the live failure (generator entered directly, skipping the gathering) and shows the rewritten descriptions correcting it, but 1/4 vs 0/5 is a weak sample - treat it as directional, not settled. A routing:orchestrator-first assertion is now mechanized in the scenario's checker and verified against these real transcripts. unknown-gate-addressed and provenance-addressed each flip in BOTH arms (P/F and F/P), so the apparent one-check regression in after-run1 is judge/agent nondeterminism, not a behavior change. Efficiency is flat: turns 5-7 before, 6 after; output tokens 5182-6659 before, 5158-5671 after.

Record: [`records/2026-07-23-nxd-generate-dp-nxd-pocket-loop-policy-read-back-gate-before.json`](records/2026-07-23-nxd-generate-dp-nxd-pocket-loop-policy-read-back-gate-before.json)
