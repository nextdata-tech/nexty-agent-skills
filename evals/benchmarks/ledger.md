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

## 2026-07-23 — nxd-generate-dp: Phase D policy-boundary gate + classification guidance (plugin v0.17.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.16.0-run1 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 7 | 5 | 5483 | 0.32 | sonnet |
| before-v0.16.0-run2 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 5367 | 0.35 | sonnet |
| after-v0.17.0-run1 | current_pack | coauthor-supplied-rubric | PASS | 12/12 | 7 | 5 | 9831 | 0.44 | sonnet |
| after-v0.17.0-run2 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 8224 | 0.39 | sonnet |

Notes: Phase D (policy-boundary gate) + the ABSENT read-back + token-matching/reachable-band guidance in derived-models.md. THIS SCENARIO DOES NOT EXERCISE PHASE D: it stops at the policy read-back before any closure is built, and Phase D runs against a LANDED closure, so the gate never executes here. Eleven of twelve checks pass identically in both arms. provenance-addressed goes 0/2 before to 1/2 after - a single flip on a check that has been noisy since it was added, not evidence of improvement. Efficiency moved the wrong way: output tokens 5367-5483 before vs 8224-9831 after (~+60%), with turns and tool calls unchanged. NOT a longer read-back - visible output is nearly identical (final answer 3501 vs 3786 chars, transcript 7831 vs 8176), so the delta is reasoning tokens, which this metric counts. Plausible cause is the ~209 added lines of reference prose (derived-models.md 482->534, self-check.md 533->690) giving the agent more to weigh; n=2 per arm cannot separate that from run-to-run variance. Worth watching on the next change that touches these files; not worth blocking on. The real evidence for Phase D is direct and outside this scenario: run against the actual defective closure from the 2026-07-23 Cowork session it FAILS with the diagnosis and fix (nxd_decisions promised but generated in the transform), passes a correct closure with no false positives, and catches the category-instead-of-status shape defect. Eight new unit tests pin each Phase D branch plus the two false starts (a version keyed on statically-parsed PHYSICAL_MODELS that passed the very closure it was written for, and a version that flagged key columns and failed every correct closure).

Record: [`records/2026-07-23-nxd-generate-dp-phase-d-policy-boundary-gate-classification-.json`](records/2026-07-23-nxd-generate-dp-phase-d-policy-boundary-gate-classification-.json)
## 2026-07-23 — nxd-generate-dp + nxd-pocket-loop: runtime credential/sensitivity artifacts and reopen-recipe fix (plugin v0.18.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-main-f57fdab | current_pack | coauthor-supplied-rubric | FAIL | 10/12 | 6 | 4 | 5293 | 0.34 | sonnet |
| before-main-f57fdab | current_pack | derive-models-from-questions | FAIL | 13/15 | 41 | 38 | 46692 | 2.68 | sonnet |
| before-main-f57fdab | current_pack | generate-runnable-dp-from-intent | PASS | 14/14 | 21 | 19 | 14403 | 1.13 | sonnet |
| after-24c3eca | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 5912 | 0.36 | sonnet |
| after-24c3eca | current_pack | derive-models-from-questions | PASS | 15/15 | 42 | 38 | 32958 | 2.76 | sonnet |
| after-24c3eca | current_pack | generate-runnable-dp-from-intent | PASS | 14/14 | 27 | 25 | 10732 | 1.10 | sonnet |

Notes: Runtime enforcement only (eval-harness work is #103). Emits .gitignore/SENSITIVE for credential-bearing closures with a Phase C gate, redacts smoke-test failures, fixes the closure reopen recipe that named nonexistent list_data_products/resume_data_product tools, and adds closure-resident credential+reopen disclosure.

**Baseline provenance:** both arms were measured against f57fdab (v0.16.0), BEFORE #104 landed Phase D and bumped the pack to v0.17.0. The branch was rebased past v0.17.0 (#104) afterwards and the entry re-titled to v0.18.0, the version it ships on, but the numbers were not re-measured — so read this table as isolating THIS change's effect on a v0.16.0 pack, not as a v0.17.0 before/after. The two changes touch disjoint mechanisms (Phase D gates policy literals in a landed closure; Phase C here gates credential-file emission), the merged self-check parses and runs both gates in sequence, and #104's eight Phase D unit tests plus the rest of evals/tests pass on the rebased branch (36/36).

**Read the derive-models-from-questions flip as noise, not as a win.** It moves FAIL->PASS (13/15 -> 15/15), but the two checks that flipped — totality-assert and key-uniqueness-assert — are judge reads of whether the *trace shows evidence* of asserts the agent wrote, and this PR does not touch the guidance behind them (derived-models.md, derivation-plan.md and transform-template.md are all unchanged; the diff is confined to the two connector refs, context-doc.md, self-check.md Phase C, reopen.md and two in-line SKILL.md invariants). The authoritative deterministic check passed in BOTH arms with zero failures, so on the mechanically-graded axis the arms are identical and the delta is agent/judge nondeterminism. Same caution as the entry above: single-run deltas here are not evidence.

None of the three scenarios exercises a credential-bearing closure, so the Phase C sensitivity gate this PR adds is unmeasured by them — its evidence is the four-case execution of the Phase C block recorded in the PR, not this table. What the table does support is the absence of a regression: verdicts hold or improve, turns are flat-to-+6, and output tokens fall on both PASS cells (46692 -> 32958, 14403 -> 10732) despite ~186 added reference lines.

Record: [`records/2026-07-23-nxd-generate-dp-nxd-pocket-loop-runtime-credential-sensitivi.json`](records/2026-07-23-nxd-generate-dp-nxd-pocket-loop-runtime-credential-sensitivi.json)

## 2026-07-24 — nxd-pocket-loop: split task-scheduling / context management + resume-first reattach (plugin v0.19.0)

Behavior pivot: reopen-is-always-a-rebuild → **resume-first reattach**
(`list_data_products` → `resume_data_product`; full rebuild only when the
published artifact is `collected` / `artifact_unavailable`). Also decomposes the
`nxd-pocket-loop` orchestrator into `reference/scheduling.md` (routing, step
order, caps, subagent fan-out) + `reference/context-and-resume.md` (reattach,
fallback, session ledger), deleting `reference/reopen.md`.

**No before/after run table — the change is not measurable by the current
harness.** The reattach path needs a live `nxd-desktop-supervisor`
(`EVAL_POCKET_SUPERVISOR_DIR` / `EVAL_POCKET_PYTHON`), and the only scenario that
exercises it, `pocket-loop-serve-query-refine`, is `ci_skip`'d and CLI-only —
its surface has no `list`/`resume` verb, so it cannot demonstrate the MCP
resume-first ordering even when run. None of the three CI-runnable public
scenarios touch the reopen/resume path. Same posture as the 2026-07-23 v0.18.0
credential-sensitivity entry above.

**Evidence instead of a table:** the deterministic gate
`evals/tests/test_resume_first_gate.py` (8 cases) pins the resume-before-build
tool ordering, the artifact-gone gating of the rebuild fallback, and the absence
of the stale three-tool framing across the skill + reference docs; it fails on a
rebuild-first revert. The full `evals/tests/` suite passes (44). The
`pocket-loop-serve-query-refine` Phase-C addition is CLI-honest (a re-serve is a
rebuild from the durable closure, narrated as such — not a reattach), with the
MCP resume-first assertion delegated to the gate test. A live before/after lands
with the next real Desktop/Cowork run.

---

## 2026-07-24 — v0.21.0 — pocket-loop offload profiling/generation to subagents

**Change:** `nxd-pocket-loop` gains a permitted path to offload Steps 2–3 (source
profiling + closure code generation) to isolated subagents — split at the
inference/authoring seam (profile subagent + generate subagent) — so the
token-heavy work and its connector references stay out of the main conversation.
The policy read-back user turn, the single-flight build, and host-side path
verification + credential injection stay on the main thread. Adds a structured
return contract, a `gap_found` bounce (both absence and profiling-ambiguity
categories), and a placeholder + host-side credential boundary.

**No before/after run table — the split is not measurable by the current
harness.** Proving generation ran in a subagent (and the read-back stayed on the
main thread) needs a fixture that does not exist: an MCP surface, a multi-source
or procedure-bearing closure, and trace access to subagent dispatch. The only
scenario exercising the loop end-to-end, `pocket-loop-serve-query-refine`, is
`ci_skip`'d, single-source, and direct-CLI — precisely the case where the skill
authors inline (offloading is permitted, not required), so it neither does nor
should exercise the split. Same posture as the v0.19.0 / v0.18.0 entries above.

**Evidence instead of a table:** the deterministic gate
`evals/tests/test_generation_subagent_gate.py` (13 cases) pins the four safety
properties at the meaning level — both `gap_found` bounce categories, every
structured-return field, `credential_slots` key-names-only, the enumerated
host-side verify file list (incl. `infra-profile.yaml`), and the two-subagent
seam split — and fails on a reworded-but-broken revert. The full `evals/tests/`
suite passes (60). The reworded orchestrator's inline path is unchanged in
behavior; a live before/after judge/turns/tokens comparison on
`pocket-loop-serve-query-refine` lands with the next real Desktop/Cowork run.

---

## 2026-07-24 — v0.22.0 — pocket-loop export_data_product handoff + public classification

**Change:** two behavior changes. (1) `nxd-pocket-loop` gains a sanctioned
outbound-sharing route — `mcp__nxd-desktop__export_data_product` — with a new
`reference/handoff-export.md`, a `Share only via export_data_product` invariant,
and a corrected credential-invariant pointer (hand-zipping a credential-bearing
closure is out; the tool's fail-closed redaction is the boundary). (2)
`nxd-generate-dp` flips every non-secret db/API connector attribute (`host`,
`port`, `database`, `schema`, `base_url`, `auth_type`, `region`) from
`public: false` to `public: true`, so an export keeps the connection topology and
redacts only the credentials the recipient refills. Confirmed against the pinned
supervisor runtime: `public:` gates **only** `export_data_product` redaction — the
transform reads every attribute via `secrets[...]` regardless — and export strips
fail-closed (`ExportParams` / the export path in
`components/desktop/supervisor/src/mcp_server.rs`; CLI `ExportOptions` in
`bin/supervisor_main.rs`).

**No before/after run table — not measurable by the current harness.** The only
scenario exercising the export half, `pocket-loop-export-handoff` (new in this
PR), is `ci_skip`'d: it needs a live `nxd-desktop-supervisor`
(`EVAL_POCKET_SUPERVISOR_DIR` / `EVAL_POCKET_PYTHON`) that CI cannot provision.
That scenario is also deliberately CSV-sourced (`attributes: []`), so it exercises
the db/API `public:` flip **zero times** — credential redaction on real secret
bytes is a documented follow-up (a db/REST-source variant that stands up the
backend during preflight). Same posture as the v0.21.0 / v0.19.0 / v0.18.0
entries above.

**Evidence instead of a table:**
- The new deterministic gate `evals/tests/test_export_public_classification_gate.py`
  (5 cases) pins the security-load-bearing classification at the meaning level:
  credentials/identity `public: false`, non-secret topology `public: true`,
  "never mark a credential `public: true`", and the confirmed runtime fact that
  `public:` controls only export redaction while the transform reads every
  attribute — failing on a silent reclassification or a revert to the old
  "supervisor drops any attribute not `public: false`" framing.
- The `pocket-loop-export-handoff` scenario's own structural checks are the
  strong-signal proof when run locally: the exported bundle carries the full
  closure + `IMPORT.md` + `export.json`, and **re-serves from the bundle alone
  and reproduces every answer** (`bundle_roundtrip_answers` all CORRECT).
- The full `evals/tests/` suite passes (65).

A live before/after on `pocket-loop-export-handoff` (and the credential-bearing
redaction variant) lands with the next real Desktop/Cowork run.

## 2026-07-27 — desktop loop: full field annotation as the default (plugin v0.23.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.22.0-run1 | current_pack | annotation-completeness-for-queryability | FAIL | 5/10 | 20 | 18 | 12151 | 0.93 | sonnet |
| before-v0.22.0-run2 | current_pack | annotation-completeness-for-queryability | FAIL | 4/10 | 17 | 15 | 8573 | 0.59 | sonnet |
| after-v0.23.0 | current_pack | annotation-completeness-for-queryability | PASS | 10/10 | 17 | 15 | 10768 | 0.68 | sonnet |

Notes: New scenario annotation-completeness-for-queryability, run against the pre-change skills (git worktree at 10278d3) and the post-change skills. Two baseline runs are recorded, not one: the first after-run was invalid (the driver script cd'd into the before-worktree and never returned, so it re-measured the old tree) and is kept as before-run2 because it independently replicates the baseline. The same five annotation checks fail in BOTH baseline runs -- unasked column left bare, status/state not disambiguated, non-additive numeric neither summed nor described, no dimension or metric carrying a description, and bare columns justified with 'no question asks for it'. The second baseline agent wrote 'left unannotated to avoid over-declaring' unprompted. After the guidance change all ten pass, with turns/tool_calls at or below both baselines, so completeness cost no extra steps. Single run per arm: check verdicts are the gate, metric deltas at this n are noise.

Record: [`records/2026-07-27-desktop-loop-full-field-annotation-as-the-default.json`](records/2026-07-27-desktop-loop-full-field-annotation-as-the-default.json)

## 2026-07-27 — desktop loop: annotation regression check on the raised-bar scenarios (plugin v0.23.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| after-v0.23.0 | current_pack | derive-models-from-questions | FAIL | 18/18 | 45 | 41 | 30342 | 2.59 | sonnet |
| after-v0.23.0 | current_pack | generate-runnable-dp-from-intent | PASS | 16/16 | 27 | 25 | 8523 | 1.22 | sonnet |

Notes: After-only, run at review request. The first ledger entry covered only annotation-completeness-for-queryability, purpose-built for this change — it shows the guidance is learnable, not that the pack did not regress where the pass bar was raised. These are the two scenarios this PR tightened most: derive-models-from-questions gained 3 checks (15 -> 18), generate-runnable-dp-from-intent gained 2 (14 -> 16) including annotations-carried-through, a DETERMINISTIC assertion in check_generated_closure.py that fails a closure outright rather than lowering a judge score. BOTH SCENARIOS PASS EVERY CHECK AT THE RAISED BAR: 18/18 and 16/16. READ THE derive-models-from-questions VERDICT COLUMN WITH THE NOTE: overall_pass is false there despite 18/18, because the harness deterministic check could not run the transform in this environment — 'invalid peer certificate: UnknownIssuer', the sandbox TLS-intercepting proxy blocking the dlt/duckdb dependency fetch. That is environmental and unrelated to annotation; every graded annotation check passed. Re-run on a runner with egress to confirm the deterministic half. No before arm: the added checks did not exist on main, so a before run would grade a different rubric; the question here is only whether the new bar is clearable, and it is.

Record: [`records/2026-07-27-desktop-loop-annotation-regression-check-on-the-raised-bar-s.json`](records/2026-07-27-desktop-loop-annotation-regression-check-on-the-raised-bar-s.json)
## 2026-07-27 — nxd-generate-dp: incremental transforms via transform_state (plugin v0.24.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.23.0 | current_pack | incremental-transform-state | FAIL | 7/16 | 35 | 33 | 23637 | 1.51 | sonnet |
| after-v0.24.0 | current_pack | incremental-transform-state | FAIL | 15/16 | 12 | 10 | 4338 | 0.47 | sonnet |

Notes: Adds reference/incremental-transforms.md: the sanctioned incremental path (durable watermark in the kernel transform_state bag; dlt pipeline state stays run-local and ephemeral). Scenario incremental-transform-state is new in this change; the before run is origin/main with the scenario, prompt and checks copied in. Both runs consulted the skill pack, so the delta isolates the new reference. 9 checks fixed, 1 regressed (preserves-transform-contract: the after agent replaced the table-name assert with the row-count check instead of keeping both, contradicting the reference which says to keep both).

Record: [`records/2026-07-27-nxd-generate-dp-incremental-transforms-via-transform-state.json`](records/2026-07-27-nxd-generate-dp-incremental-transforms-via-transform-state.json)

## 2026-07-28 — nxd-review-closure: adversarial review round over an authored closure (plugin v0.25.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| control-no-review | no_review_control | treasury-yield-curve | FAIL | 16/17 | 35 | 31 | 65563 | 5.32 | claude-opus-4-8 |
| reviewed-run1 | current_pack | treasury-yield-curve | FAIL | 16/17 | 34 | 30 | 63574 | 5.07 | claude-opus-4-8 |
| reviewed-run2 | current_pack | treasury-yield-curve | FAIL | 16/17 | 31 | 28 | 63722 | 4.83 | claude-opus-4-8 |

Notes: NO MEASURABLE CORRECTNESS EFFECT at N=1 per arm; recorded as such rather than as a win. All three runs scored 16/17 on treasury-yield-curve, but they did not fail the same check: control failed tier2-measure-reconciliation, reviewed-run1 failed determinism-rerun-verdict while PASSING tier2, and reviewed-run2 failed tier2 again. Two checks moved, not one. tier2 going FAIL -> PASS -> FAIL across runs whose two reviewed cells shared an identical skill-set, prompt and scenario makes it unstable rather than responsive to the review round; an earlier reading of run1 alone as a win was withdrawn. reviewed-run1's determinism failure is ENVIRONMENTAL, not a content failure: the installed supervisor had baked NXD_DESKTOP_REPO_ROOT to a deleted worktree, so its build-1 aborted before the transform ran. It is kept in the table rather than dropped, because removing a run that contradicts the other would misrepresent the evidence. What the runs do support: no correctness regression, and no efficiency regression - the reviewed runs used FEWER main-thread turns and tokens than the control (31-34 vs 35 turns, ~3% fewer output tokens, 5-9% cheaper), so dispatching the review subagent did not add turns to the orchestrator. The anti-signal this experiment was designed to catch - the reviewed arm scoring worse because the builder accepted fabricated critique instead of adjudicating it - did not appear. The scenario had only one check of headroom (control 16/17) because a prompt-extraction fix in this same PR raised the control from an earlier ~14/17, so this instrument could not have shown a large effect; N>=5 per arm, or a scenario with more semantic headroom, is needed for a real verdict. Model note: all three cells ran on claude-opus-4-8, NOT the sonnet passed to --agent-model - run.py's effective_agent_model pins a model per scenario for pocket-path scenarios and overrides the flag, which the per-report scenario_agent_models field records. Runtime caveat: control ran on supervisor db0e8ab3a / wheels 0.41.143 and reviewed-run2 on 173737f6c / 0.41.144 after rebuilding from main, which is a confounder between those two cells.

Record: [`records/2026-07-28-nxd-review-closure-adversarial-review-round-over-an-authored.json`](records/2026-07-28-nxd-review-closure-adversarial-review-round-over-an-authored.json)
## 2026-07-28 — nxd-dp-static-artifact: read-only tool bridge fallback for clients without MCP resource primitives (plugin v0.25.1, superseded below by the v0.25.2 run)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.25.0 | current_pack | dp-static-artifact-lifecycle | FAIL | 4/5 | 17 | 15 | 12287 | 0.53 | sonnet |
| after-v0.25.1 | current_pack | dp-static-artifact-lifecycle | FAIL | 5/6 | 20 | 18 | 11936 | 0.57 | sonnet |

Notes: Adds a two-transport read strategy: native MCP resource ops preferred, list_data_product_resources/read_data_product_resource used only when the client exposes no resource primitives. New scenario check one-read-transport passes in the after run (5/6 vs 4/5). Both runs fail the SAME pre-existing deterministic HTML check (a required substring the generated page omits), unrelated to this change — no regression.

Record: [`records/2026-07-28-nxd-dp-static-artifact-read-only-tool-bridge-fallback-for-cl.json`](records/2026-07-28-nxd-dp-static-artifact-read-only-tool-bridge-fallback-for-cl.json)

## 2026-07-28 — nxd-dp-static-artifact: visual-channel and absence-state render rules (plugin v0.25.2)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | agent |
|---|---|---|---|---|---|---|---|---|
| before-v0.25.1 | current_pack | dp-static-artifact-lifecycle | FAIL | 5/6 | 20 | 18 | 11936 | sonnet |
| after-v0.25.2 | current_pack | dp-static-artifact-lifecycle | PASS | 6/6 | 21 | 19 | 8491 | sonnet |

Notes: FIRST PASSING RUN of this scenario — the prior entry's both-arms-FAIL was
not a property of the skill but of the gate. `check_static_artifact.py` required
heading and formatting vocabulary the skill contract never prescribes
(`"output ports"`, `"output-level models"`, `"min: 0"`), so an agent following
the prose failed while only the example asset could pass. The gate now derives
required sections from the contract's render order, matches headings tolerantly,
and asserts constraints/output-level surfaces structurally rather than by
punctuation. Ordering, union-avoidance and escaping assertions are unchanged.

The behaviour change this measures (`e83fab3` + this commit): no drawn or named
relationship without a declared join, per-value absence glosses including the new
`"" · empty`, omit-all-absent columns, and a viewport clamp. Fixture extended
with a `support_tickets` model carrying `description: ""`, a `null`-description
attribute, a `customer_id` shared with the other models but declaring NO join,
and per-model `joins: null` — so the new rules have something to bite on. Two
intermediate runs failed on real skill defects the strengthened fixture exposed
(a dropped `null` gloss), fixed by making the gloss obligation explicit in
SKILL.md rather than by relaxing the check.

Output tokens fell ~29% (11936 → 8491) while checks went 5/6 → 6/6; single-run
deltas are noise per the header, so read the verdict, not the efficiency.

**CORRECTION (same day):** the `after-v0.25.2` PASS above was a single run and
did not replicate — four further runs of that same content gave 1 PASS / 4 FAIL
on the absence gloss. The gate fixes in that commit stand; the absence rule did
not, and is fixed in the entry below. Do not cite this row's PASS as evidence.

Record: [`records/2026-07-28-nxd-dp-static-artifact-visual-channel-and-absence-state-render-rules.json`](records/2026-07-28-nxd-dp-static-artifact-visual-channel-and-absence-state-render-rules.json)

## 2026-07-28 — nxd-dp-static-artifact: absence rule branches on the key (plugin v0.25.2)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | agent |
|---|---|---|---|---|---|---|---|---|
| before (prose rule) ×5 | current_pack | dp-static-artifact-lifecycle | FAIL ×4, PASS ×1 | 5/6, 6/6 | 16–23 | 14–21 | 11.9–18.5k | sonnet |
| after (key-branch + grep) ×5 | current_pack | dp-static-artifact-lifecycle | PASS ×5 | 6/6 | 15–26 | 13–24 | 9.1–13.1k | sonnet |

Notes: N=5 PER ARM, deliberately — the entry above this one recorded a single
PASS and was WRONG. Re-running that same content four more times gave 1 PASS /
4 FAIL, all on the same assertion (a `null` gloss absent from the whole page).
One green run on a nondeterministic agent is not evidence; this scenario needed
N≥4 before its verdict was stable either way.

Two root causes, found by diffing what the passing runs did. (1) The render step
said to show a description "where present", which licenses dropping a `null`
one — the agent was following the more specific instruction correctly. "Present"
now means the KEY exists, and the rule is a two-branch decision (absent key →
render nothing; present key → always render, gloss included) rather than five
sentences of prose carrying a rule, an anti-rule and an exception. (2) Both
passing runs ran a grep-style verification pass over the finished file; two of
the three failures skipped it. Grepping the temp file for every gloss the bundle
needs is now part of validating it before the atomic rename, stated in the
file-and-safety contract rather than only in the handoff checklist.

Efficiency moved the right way as a side effect (mean output tokens 14.9k →
11.2k), but read the verdict column, not that: the point of this entry is 1/5 →
5/5 on correctness.

Record: [`records/2026-07-28-nxd-dp-static-artifact-absence-rule-branches-on-the-key.json`](records/2026-07-28-nxd-dp-static-artifact-absence-rule-branches-on-the-key.json)

## 2026-07-28 — v0.25.3 — nxd-data-product-builder: keyword `schema=` for `snowflake_config`

**Change:** doc correctness across the builder skill's Snowflake surface, forced by
an upstream signature change. `nxd.spec.snowflake_config` became
`snowflake_config(database=None, schema=None)` — `database` is now the FIRST
parameter and both are optional (nextdata-tech/nxd#7321). Every positional call
site in the pack therefore bound a schema name to `database` and left `schema` at
its default. Neither spec-build nor launch errors: the port writes to
`<intended-schema>.<data-product-name>` where a database of that name exists, and
otherwise fails at the driver with a database-not-found error naming the value the
author meant as the schema. Fixed the two `data_product_spec.md` snippets, the
`promises-contracts.md` snippet, the `policy-compliance-failure` eval fixture, and
the signature table (which still described the pre-change single-argument form);
added a worked `database` example plus the positional-binding pitfall to
`data_product_spec.md`, `storage-configs.md` and `common-pitfalls.md`; and bumped
the `nextdata-public-examples` submodule so the bundled examples the pack tells
agents to imitate no longer demonstrate the positional form.

**No before/after run table — not measurable by the current harness.** The
`policy-compliance-failure` cell did move FAIL -> PASS across the PR runs, but that
is NOT attributable to this change and is deliberately not presented as evidence:
none of that scenario's five checks observe `snowflake_config`'s schema/database
binding (they cover identifying the policy type, separating input expectations from
output promises, adding an enforced quality promise, `nxd activate policy` flag
shape, and the verify commands). The fixture edit changes one line of the STARTING
spec that no check reads, so the flip is run-to-run variance on n=1 before and n=2
after. The baseline is left at FAIL accordingly.

No table for the reference-doc edits themselves: no scenario asserts on
`snowflake_config` call shape, so the harness cannot distinguish the keyword form
from the positional one — the failure it prevents lands at runtime as a wrong
target or a driver-side error, neither of which an offline check observes. Same posture as the v0.22.0 / v0.21.0
entries above.

**Evidence instead of a table:**
- `scripts/validate_skills.py` passes; version surfaces agree at 0.25.3 across
  `plugin.json`, `marketplace.json` and all 15 `SKILL.md`.
- `./build-skills.sh` packages every skill `ok`; `nxd-data-product-builder` is 168
  entries after the submodule bump, under the 200-entry cap.
- No positional `snowflake_config(` survives in any repo-owned file or in the
  bumped submodule; the only positional forms left are the quoted anti-examples in
  the new pitfall prose.
- Signature verified against the upstream source, not inferred:
  `components/nxd_py/data_product/nxd/spec/__init__.py::snowflake_config` and
  `_spec.py::SnowflakeConfig.__init__` (both parameters `Optional[str] = None`),
  with the driver-side fallback that makes the mistake silent in
  `driver_impls/drivers/nxd-snowflake/src/storage/mod.rs` (absent `schema` falls
  back to the data-product name rather than erroring).

## 2026-07-29 — v0.25.4 — nxd-generate-dp: per-criterion score explainability and absence semantics

**Change:** reference-doc rules for `nxd-generate-dp`. `derived-models.md` gains the
explanation-row contract (a scored row carries per-criterion rows saying WHY it scored
what it did) and a precedence section for the case where a supplied rubric's bottom
band is the absence case — the band that decides whether "no evidence" scores the
minimum or is held out of the score entirely. `llm-judgments.md` picks up the matching
vocabulary so the two documents describe one model rather than two.

The explanation row's authored-by column is named `evidence_kind` (`fact` /
`inference`), deliberately NOT `provenance`: `nxd_decisions.provenance` (v0.25.5)
classifies who authored a RULING, while this classifies what a per-criterion
explanation is standing on. Two different questions; giving them one name would make
the ledger unreadable at the exact point a reviewer needs to tell them apart.

**No before/after run table — no scenario observes these rules.** Nothing in
`evals/public/` asserts on explanation rows, `evidence_kind`, or bottom-band absence
precedence; a grep across every `checks.json` and every deterministic checker returns
nothing. The harness therefore cannot distinguish a run that follows the new
precedence from one that does not — the failure these rules prevent is a scored
absence silently reading as a genuine low score, which no current check inspects.
Reporting a table from scenarios blind to the change would be noise presented as
signal. Same posture as the v0.25.3 and v0.22.0 entries above.

**Evidence instead of a table:**
- `scripts/validate_skills.py` passes; version surfaces agree at 0.25.4 across
  `plugin.json`, `marketplace.json` and all 17 `SKILL.md`.
- `./build-skills.sh` packages every skill `ok`; `nxd-generate-dp` is 18 entries and
  `nxd-data-product-builder` 159, both under the 200-entry cap.
- Both touched reference files added their new sections to the existing `## Contents`
  list, so progressive disclosure still resolves them.
- `src/nxd-generate-dp/SKILL.md` is at exactly 500 lines, the cap, after restoring the
  Step 6b dispatch that a rebase had dropped.
- The three asserts the rules require are separately falsifiable: coverage is read off
  the score sheet rather than off the explanation rows (so a missing explanation
  cannot hide as a missing score), the scored-absence pair, and a substring anchor
  that survives whitespace and case differences.

**Follow-up worth doing:** these rules are unmeasurable only because no scenario
exercises them. A scenario asserting on explanation rows and bottom-band precedence
would convert every future change here from evidence-prose into a real table.

## 2026-07-29 — v0.26.0 — nxd-generate-dp: ruling provenance classes in `nxd_decisions`

**Change:** `nxd_decisions` gains a mandatory `provenance` column alongside `status`.
Settled-or-not and authored-by are separate axes: a ruling the agent invented to fill
a gap and a ruling the user supplied can both be `confirmed`, and only `provenance`
tells the reader which one they are ratifying. Phase D fails a closure whose ledger
lacks the column or carries an out-of-vocabulary value, and four new deterministic
checks land in `check_coauthored_closure.py`.

**No before/after run table — the change is not measurable on a shared denominator.**
The four new checks (`provenance-column-present`, `provenance-vocabulary-valid`,
`agent-authored-ruling-classified`, `user-supplied-ruling-classified`) did not exist
before this PR, so a "before" run cannot be scored against them: every prior closure
fails a column that was not required of it. Scoring the after-run against the larger
check set and calling the difference an improvement would measure the denominator
change, not the skill. Same posture as the 2026-07-23 Phase D entry, which recorded
the same situation rather than inventing a comparison.

**Evidence instead of a table:**
- `scripts/validate_skills.py` passes; version surfaces agree at 0.26.0 across
  `plugin.json`, `marketplace.json` and all 17 `SKILL.md`.
- `./build-skills.sh` packages every skill `ok`; `nxd-data-product-builder` is 159
  entries, under the 200-entry cap.
- Phase D gate tests: 26 passed across `test_policy_boundary_phase_d.py` and
  `test_deterministic_check.py`, including the pair that pins the two axes as
  independently checked — `test_status_and_provenance_are_checked_independently`
  and `test_missing_provenance_still_reports_bad_status`. Without that pair a
  nested check would report only the first failing axis and leave half the ledger
  ungraded.
- Vocabulary is closed and case-sensitive: `Confirmed` / `User_Confirmed` are
  rejected, and a short row or empty cell is caught as `''` rather than passing.
- Known inherited limit, not introduced here: a header-only CSV with zero data rows
  skips both column checks. The gate is row-driven, so an empty ledger is not a
  failure on either axis.

## 2026-07-29 — v0.26.1 — semantic roles + the `Agg.EXPRESSION` boundary (#130)

**Change:** two things, both doc-only but both behavior-bearing. (1) A new
**Semantic roles** section in `nxd-data-product-builder`'s
`semantic_model_spec.md` — the role table (`primary_key` / `dimension` / `join`),
the three accepted `.schema()` field shapes, and the rule that agent-visible
descriptions belong on `dimension(description=…)` / `metric(description=…)`, not
on `field(description=…)`. (2) `Agg.EXPRESSION` promoted from "never use it" to a
documented member with an explicit boundary, which required reconciling four
files that disagreed about it.

The pack previously contradicted itself in three places once EXPRESSION was
documented, all fixed here: `nxd-generate-dp/reference/nxd-spec-api.md` wrongly
documented `expressions=` on `data_product_output().model(...)`;
`nxd-semantic-data-product/reference/registry-authoring.md` asserted a closed
six-member vocabulary as an API fact; and that skill's
`compiler-and-routing.md` Snowflake table had no EXPRESSION row. The
`median` prohibition is retained and strengthened — `Agg.EXPRESSION` is
explicitly ruled out as a smuggling route for it.

**No before/after run table — not measurable by the current harness.** No eval
scenario authors an `Agg.EXPRESSION` metric or asserts on description placement,
so the harness cannot distinguish the corrected guidance from the old text. The
failures these edits prevent land at author time (an expression map silently
dropped, so the metric compiles and then emits wrong SQL) or at agent-read time
(two loaded skills giving opposite rulings) — neither is observable offline.
Same posture as the v0.25.3 / v0.22.0 / v0.21.0 entries above.

**Evidence instead of a table:**
- `scripts/validate_skills.py --root .` passes; version surfaces agree at
  0.26.1 across `plugin.json`, `marketplace.json` and all 17 `SKILL.md`.
- `./build-skills.sh` packages all 17 skills `ok`; largest is
  `nxd-mesh-analyzer` at 32 entries, far under the 200-entry cap.
- Signatures verified against upstream `nxd` source, not inferred:
  - `Agg.EXPRESSION` is a real member —
    `components/nxd_py/data_product/nxd/experimental/semantic/registry.py:22-31`,
    mirrored in Rust at `components/shared/semantic_registry/src/types.rs:43-58`.
  - `expressions=` persists **only** on the port model
    (`nxd/spec/_spec.py:3166-3173`); `data_product_output().model(...)`
    validates and discards it (`_spec.py:4661-4667`), pinned upstream by
    `test_output_models.py:96`
    (`test_output_model_expressions_are_not_written_to_top_level_metadata`).
    This is why the old `nxd-spec-api.md` guidance would have silently no-opped.
  - Expression SQL resolution and the EXPRESSION dialect row —
    `nxd/experimental/semantic/dialect.py:144-173` (an attached expression wins
    for any `Agg`; bare `Agg.EXPRESSION` emits `column` as raw SQL). Build-time
    guard at `registry.py:1067-1078`.
  - Description routing — `dimension(description=…)` lands in the role blob and
    is what `describe_model` surfaces (`registry.py:334-344`,
    `_manifest_compile.py:440`); `field(description=…)` lands on
    `AttributeSpec._description` (`nxd/spec/_semantic.py:314-357`) and never
    reaches the querying agent.
  - `SamplingMethod` members are PascalCase on the `nxd.spec` surface
    (`nxd/core/yaml_schemas.pyi:1553-1556`), correcting the one table row that
    said `RANDOM`. A second SCREAMING_CASE enum of the same name exists at
    `nxd/core/_bindings.pyi:780-783` but is not what `nxd.spec` re-exports.
- Phase A gate: `Agg.EXPRESSION` parses as a known member but `walk_roles`
  emits a targeted `bad()` naming the derivation-plan boundary, so the gate now
  AGREES with the prose in `nxd-spec-api.md`, `derivation-plan.md` and
  `nxd-generate-dp/SKILL.md` instead of silently passing the construct they
  forbid. This also removes a gate/grader split: the vendored grader
  `evals/public/generate-semantic-layer-from-live-source-and-questions/fixtures/check_semantic_model.py:46`
  keeps `AGGS` at the six lowercase names and fails an `expression` metric at
  its `role-grammar` check, so a closure reaching for it would previously have
  passed its own self-check and then failed the eval.
  Verified on a two-closure fixture: an `Agg.EXPRESSION` metric yields
  `models.py:order_metrics.net_revenue: Agg.EXPRESSION is outside this
  generation path ...`, while the same closure using `Agg.SUM` produces no
  `Agg` diagnostic. `scripts/self_check.py` and the fenced mirror in
  `reference/self-check.md` were diffed programmatically and are byte-identical.
- Builder port surface corrected: `data_product_spec.md:357` documented the
  port method as `.model(model)` with no `expressions`, which is what made the
  new example look like a `TypeError`. The real signature is
  `.model(model, is_public=True, expressions=None)` (`_spec.py:3166-3173`).
  The worked example now also puts `.promise()` at port level, per
  `troubleshooting.md:102` (output-level promises are silently ineffective),
  while keeping a model registered at output level as validation requires.

## 2026-07-30 — nxd-generate-dp: transform_state is the only route; watermark fallback deleted (plugin v0.26.2)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.26.0 | current_pack | incremental-multi-model | PASS | 15/15 | 32 | 29 | 56499 | 3.84 | claude-opus-4-8 |
| before-v0.26.0 | current_pack | incremental-transform-state | PASS | 16/16 | 22 | 20 | 8059 | 0.69 | sonnet |
| before-v0.26.0 | current_pack | incremental-transform-state | PASS | 16/16 | 13 | 11 | 4364 | 0.50 | sonnet |
| before-v0.26.0 | current_pack | incremental-transform-state | FAIL | 5/16 | 17 | 15 | 7501 | 0.49 | sonnet |
| before-v0.26.0 | current_pack | incremental-transform-state | PASS | 16/16 | 13 | 11 | 3810 | 0.38 | sonnet |
| before-v0.26.0 | current_pack | incremental-transform-state | FAIL | 5/16 | 23 | 21 | 9320 | 0.64 | sonnet |
| before-v0.26.0 | current_pack | incremental-transform-state | PASS | 16/16 | 10 | 9 | 3868 | 0.38 | sonnet |
| before-v0.26.0 | current_pack | incremental-transform-state | PASS | 16/16 | 25 | 23 | 8272 | 0.75 | sonnet |
| before-v0.26.0 | current_pack | incremental-transform-state | FAIL | 15/16 | 16 | 14 | 5934 | 0.58 | sonnet |
| before-v0.26.0 | current_pack | incremental-transform-state | PASS | 16/16 | 14 | 12 | 5337 | 0.54 | sonnet |
| before-v0.26.0 | current_pack | incremental-transform-state | PASS | 16/16 | 14 | 12 | 4708 | 0.52 | sonnet |
| after-v0.26.2 | current_pack | incremental-transform-state | PASS | 16/16 | 12 | 10 | 4177 | 0.46 | sonnet |
| after-v0.26.2 | current_pack | incremental-transform-state | FAIL | 5/16 | 41 | 39 | 13672 | 1.29 | sonnet |
| after-v0.26.2 | current_pack | incremental-transform-state | PASS | 16/16 | 17 | 15 | 6940 | 0.58 | sonnet |
| after-v0.26.2 | current_pack | incremental-multi-model | FAIL | 14/15 | 33 | 30 | 21198 | 1.86 | claude-opus-4-8 |
| after-v0.26.2 | current_pack | incremental-transform-state | FAIL | 14/16 | 15 | 13 | 5144 | 0.59 | sonnet |
| after-v0.26.2 | current_pack | incremental-transform-state | PASS | 16/16 | 13 | 11 | 4867 | 0.51 | sonnet |
| after-v0.26.2 | current_pack | incremental-transform-state | FAIL | 15/16 | 15 | 13 | 6030 | 0.58 | sonnet |
| after-v0.26.2 | current_pack | incremental-transform-state | PASS | 16/16 | 15 | 13 | 4812 | 0.59 | sonnet |
| after-v0.26.2 | current_pack | incremental-transform-state | FAIL | 6/16 | 23 | 21 | 8245 | 0.62 | sonnet |
| after-v0.26.2 | current_pack | incremental-transform-state | PASS | 16/16 | 12 | 10 | 4762 | 0.49 | sonnet |
| after-v0.26.2 | current_pack | incremental-transform-state | FAIL | 5/16 | 22 | 20 | 8270 | 0.85 | sonnet |

Notes: Before arm is origin/main at 81848fc (v0.26.0), which is NOT this PR's merge base -- the branch was later rebased onto 39b0216 (v0.26.1). That delta is 41 files, not the four an earlier version of this note listed. Skill-side it is semantic-layer / Agg.EXPRESSION material (nxd-generate-dp/SKILL.md, derivation-plan.md, nxd-spec-api.md, self-check.md, plus semantic_model_spec.md, compiler-and-routing.md and registry-authoring.md inside current_pack) with no bearing on incrementality. It ALSO changes the harness -- evals/run.py, evals/eval_backends.py, scripts/self_check.py (15 files, +3484 lines under evals/ and scripts/) -- so the arms were not run by identical harness code, which the earlier 'the arms remain comparable' sentence obscured. Most of that is gated on scripted turns (empty for both incremental scenarios), but one change is not: _tool_input_json() now hoists `command` to the front before the 600-char truncation that renders every trace the judge reads. It is unlikely to explain the after-only readback failures, since Edit inputs carry no `command` key and render byte-identically across arms while the cited rationales are all about Edit content -- but it is transcript-visible, it is exactly the machinery this note blames for those failures, and it is disclosed here rather than left to be discovered. 

TWO EARLIER VERSIONS OF THIS ENTRY WERE WRONG AND ARE RETRACTED HERE. (1) The first baselined against fb0d472 -- this branch's own gated-fallback commit, not main -- and reported incremental-multi-model as FAIL 13/15 to PASS 15/15; against real main that scenario was ALREADY PASS 15/15, so the deletion never improved it. (2) The second reported the head arm's deciding cell as 2/4 after merging two report files without recounting; the correct figure at the time was 3/5. NOTE both that 3/5 and the 'after-deletion' arm it described belong to SUPERSEDED versions of this record (ledger commits 2afb9df and 659d5d2) -- neither appears in the record linked below, whose arms are before-v0.26.0 and after-v0.26.2 only. Cite those commits, not this record, to check the retracted figures. Both errors overstated a regression. 

incremental-transform-state is bimodal on consults-the-skill-pack: runs that open the pack score 14-16/16, the rest 5-8/16 (they conclude from public docs that transform_state is k8s-only). THE CELL IS DEFINED BY THAT CHECK PASSING, NOT BY THE SCORE BAND -- keying on the check reproduces the cell sizes exactly (8 before, 7 after, 2 in the probe), and only that cell measures the doc. At N=8 before / N=7 after in that cell: before 7/8 at 16/16 (16 x7, 15 x1), after 5/7 (16 x5, 15, 14). That is a ONE-SAMPLE difference and NOT distinguishable at this N -- and note the baseline is NOT immaculate: its own 15/16 run disproves the earlier 'perfect 4/4' framing that made the gap look real. 

Residual failures, counted INSIDE the consulting cell (the only cell this paragraph claims measures the doc): readback-avoids-module-shadowing-and-first-run-io 0 before / 2 after; first-run-empty-bag-takes-history 0 before / 1 after. Pooled over all 10 runs per arm the latter reads 2 before / 4 after, but 2 of 2 and 3 of 4 of those are the 5-6/16 non-consulting runs, which fail ~11 checks each because they never opened the pack -- so the pooled figure is non-consulting noise and an earlier version of this note reported it as a doubling in a check that did NOT regress in the measuring cell. readback is the only check that moved there. 

CONFOUND PROBE (the review's suggested experiment, run 2026-07-30): a third arm at the TRUE merge base 39b0216 with the CURRENT checks.json copied in -- removing both the wrong-baseline and pre-rewrite-rubric confounds -- put 2 of 6 runs in the consulting cell (16, 15) and readback failed 1 of those 2. So readback CAN fail on a pre-change tree once judged under current rubric text, where the 81848fc baseline showed 0 of 8. That materially weakens the 0-before/2-after reading as evidence of a real effect and supports the confound explanation. It does NOT settle it: N=2 in the cell is far too thin to estimate a rate, and this arm cannot separate the baseline-commit confound from the rubric one since it removes both at once. Anyone re-testing should target N>=8 IN THE CELL (expect to run ~24 samples given the bimodality) at 39b0216 with current rubric. The probe's 6 runs are committed at records/2026-07-30-confound-probe-mergebase-39b0216-current-rubric.json, so this arm is checkable rather than asserted. 

An earlier version of this note claimed BOTH appear in the baseline and inferred 'a property of the scenario's judgeability, not of this change' -- that is RETRACTED: it holds for first-run-empty-bag-takes-history, which does fail in the baseline, but readback-avoids-module-shadowing-and-first-run-io fails ZERO times before and twice after, so the generalisation was wrong and it pointed in this change's favour. Only 2 of the failing instances are genuinely missing-evidence judgements (readback on the 6th incremental-transform-state run of the after arm, 'the Edit's new content is never shown'; empty-bag on the 4th, 'truncated before the function body' -- numbered over that scenario's runs only, NOT over the table rows, which interleave one incremental-multi-model row); the rest are the judge recording that no state read-back appeared at all, and one readback instance explicitly notes the aliasing WAS visible. So 'all about Edit content' was too broad. Narration volume does not separate passing from failing runs either, so the mechanism is unexplained -- but for the readback check the after-only distribution is NOT evidence against a real effect, and nothing here rules one out. 

preserves-transform-contract, the one check that genuinely regressed on the deletion arm (failed both 14/16 runs there -- see ledger commit 659d5d2 for that arm's rows), fails 1 of 10 before and 0 of 10 after here, i.e. the keep-both rewording holds. incremental-multi-model: PASS 15/15 on main, PASS 15/15 after the deletion, 14/15 on the head commit failing only closure-still-builds. An earlier version of this note called that failure 'environmental' and said it was 'not asserted as a doc regression' -- BOTH are RETRACTED. The committed rationale is a closure-design failure, not infrastructure: the agent demoted the non-append-safe lane aggregate to a consume-time semantic_view, left PHYSICAL_MODELS/DERIVED_MODELS unchanged so no summary table is landed or row-count-verified, and added an expedited_flag column to the now append-only shipments table with no backfill for already-landed rows. That is precisely what closure-still-builds exists to catch (this ledger reserves 'environmental' for infrastructure faults -- see the 2026-05 entry's UnknownIssuer proxy failure). A doc-side cause was live: at the time of this arm the gate neither sanctioned nor forbade escaping it by demoting an aggregate to a query-time view, and at N=1 the run cannot decide whether that silence caused the failure. The SAME commit that records this retraction (9f64227) closes that gap -- incremental-transforms.md now forbids the demotion route explicitly -- so the doc being merged is no longer silent on it. ARM VINTAGE, stated because it bounds every claim above: the after-v0.26.2 arm was run at 850e4e0, and EVERY commit on this branch after 850e4e0 that touches src/ or evals/public/ is unbenchmarked -- the exact number grows with every review round, so this note deliberately does not state one -- compute it with `git log --oneline 850e4e0..HEAD -- src/ evals/public/`. Earlier versions said three, then eighteen, then twenty; each went stale the round after it was written, which is the point. Everything those commits changed is unbenchmarked, including three rule changes rather than clarifications: the gate-escape prohibition (9f64227), the one-pipeline-object rule (32fdf36), and the first-run bullet's move from 'avoid flat access on a path that can execute on run one' to 'wrong at every model count and on every run' (c394af1). They are doc rules added in response to failures THIS arm recorded, which is the intended direction, but no run covers the tree being merged. 

The agent column is now sourced per run from metrics.agent_model (benchmark_record.py previously read the report-level field and mislabelled these rows sonnet). incremental-multi-model ran on claude-opus-4-8 in every arm: run.py's effective_agent_model() returns the pinned POCKET_AGENT_MODEL for any pocket-path scenario on the Claude backend, and incremental-multi-model has fixtures/pocket.json, so it cannot have run on anything else. (Do NOT verify this from the after arm's scenario_agent_models -- that field carries only the incremental-transform-state entry, because each arm's top-level metadata came from ONE of the merged report files.) Same cause, one more caveat: every arm-level field (elapsed_s, agent_model) describes only the first merged file, NOT the concatenated results -- the after arm reads elapsed_s 110.2 against 11 results. The per-run rows are intact and reconcile against the table, so no figure here is affected, but recomputing from arm-level metadata would mislead. 

ROUND-TRIP PROVENANCE (moved here out of the shipped doc, which should not carry cross-repo source paths): the kernel claim is pinned by transform_state_round_trips_across_two_builds_of_one_workflow in the nxd repo's components/desktop/supervisor/tests/acceptance.rs -- run 1 commits a counter, run 2 asserts prior_bag == {run_counter: 1}. Verified live on 2026-07-30: run1 prior_bag {} counter 1, run2 prior_bag {run_counter: 1} counter 2. The case is Python-gated, so it runs locally rather than in CI. 

RUBRIC DRIFT, disclosed in full: three checks in incremental-transform-state/checks.json were reworded across this branch -- state-bag-addressed-via-for-model, verification-can-detect-a-missing-write, readback-avoids-module-shadowing-and-first-run-io -- plus uses-transform-state-kwarg, so the before arm ran against pre-rewrite text for all four. TWO of the four pass conditions tightened, not one: uses-transform-state-kwarg and verification-can-detect-a-missing-write both gained the SELECT max(<cursor>) read-back as a banned alternative. A FIFTH rewording is in a DIFFERENT file this paragraph previously omitted -- incremental-multi-model/checks.json's own uses-transform-state-kwarg, tightened the same way in 6bdb3b0 so the sibling scenario stops grading the rule more loosely. No previously-passing solution changes verdict, since no run in either arm reconstructed its cursor that way, and none of the four checks ever REQUIRED the banned shape. But the arms were not judged against byte-identical check text, and one condition is narrower on the after side.

Record: [`records/2026-07-30-nxd-generate-dp-transform-state-is-the-only-route-watermark-.json`](records/2026-07-30-nxd-generate-dp-transform-state-is-the-only-route-watermark-.json)

## 2026-07-31 — nxd-generate-dp: round-two Pocket CSV runtime contract fixes (plugin v0.27.0)

**SUPERSEDED — measures the PRE-REBASE implementation.** This work was rebased onto the spec-authoritative architecture (#139) and substantially reworked: the contract inventory moved from `CONTEXT.md` into `## expectations` / `## promises` sections of the dp-spec IR, the Phase C gate was rewritten against registered `closure.*` codes, and the infra-profile gate that this PR's review flagged as hard-failing every non-CSV profile was re-scoped. The numbers below were real when taken; they no longer describe the shipped code. Preserved as history — see the 2026-08-02 entry for the rebased branch, which explains why the protected scenario could not be re-run.


| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| baseline-main-current-rubric | current_pack | api-to-vector-data-product-build | PASS | 6/6 | — | 38 | 31098 | — | gpt-5.6-terra |
| baseline-main-current-rubric | current_pack | generate-runnable-dp-from-intent | FAIL | 7/16 | — | 15 | 9757 | — | gpt-5.6-terra |
| baseline-main-current-rubric | current_pack | policy-compliance-failure | PASS | 5/5 | — | 13 | 6020 | — | gpt-5.6-terra |
| head-initial | current_pack | api-to-vector-data-product-build | FAIL | 4/6 | — | 20 | 18935 | — | gpt-5.6-terra |
| head-initial | current_pack | generate-runnable-dp-from-intent | FAIL | 15/16 | — | 22 | 10549 | — | gpt-5.6-terra |
| head-initial | current_pack | pocket-custom-contracts | FAIL | 4/5 | — | 18 | 11161 | — | gpt-5.6-terra |
| head-initial | current_pack | policy-compliance-failure | PASS | 5/5 | — | 14 | 5620 | — | gpt-5.6-terra |
| head-path-fixed | current_pack | generate-runnable-dp-from-intent | PASS | 16/16 | — | 18 | 10227 | — | gpt-5.6-terra |
| head-path-fixed | current_pack | pocket-custom-contracts | PASS | 5/5 | — | 16 | 14823 | — | gpt-5.6-terra |
| head-api-rerun | current_pack | api-to-vector-data-product-build | ERROR | — | — | — | — | — | gpt-5.6-terra |

Notes: Current-rubric baseline versus round-two review fixes. **The `pocket-custom-contracts` rows are retracted and superseded by the source-isolated 2026-08-02 entry below** because these runs did not prove answer-source isolation; do not cite their Pocket verdicts or efficiency metrics. Non-Pocket rows retain their original status. The initial head arm resolved uv through an unconfigured asdf shim for generate-runnable and Pocket; PATH-fixed reruns passed 16/16 and 5/5. API initial was 4/6 from an agent-authored port-name error; its repeat hit the harness 1200s agent timeout before evidence or judging completed, so no API pass is claimed.

Record: [`records/2026-07-31-nxd-generate-dp-round-two-pocket-csv-runtime-contract-fixes.json`](records/2026-07-31-nxd-generate-dp-round-two-pocket-csv-runtime-contract-fixes.json)

## 2026-07-31 — spec-authoritative closures: CONTEXT.md retired for a byte-copied dp-spec.approved.md + lock + generated build-record.json (plugin v0.28.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.27.0 | current_pack | coauthor-executable-policy-readback | FAIL | 13/15 | 22 | 18 | 41478 | 2.20 | sonnet |
| before-v0.27.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 8716 | 0.43 | sonnet |
| before-v0.27.0 | current_pack | pocket-loop-export-handoff | ERROR | — | — | — | — | — | sonnet |
| before-v0.27.0 | current_pack | coauthor-executable-policy-readback | FAIL | 13/15 | 28 | 24 | 46823 | 2.45 | sonnet |
| before-v0.27.0 | current_pack | coauthor-supplied-rubric | FAIL | 9/12 | 12 | 10 | 22438 | 0.93 | sonnet |
| before-v0.27.0 | current_pack | pocket-loop-export-handoff | ERROR | — | — | — | — | — | sonnet |
| before-v0.27.0 | current_pack | coauthor-executable-policy-readback | FAIL | 12/15 | 52 | 48 | 83001 | 5.16 | sonnet |
| before-v0.27.0 | current_pack | coauthor-supplied-rubric | FAIL | 9/12 | 13 | 11 | 21521 | 0.95 | sonnet |
| before-v0.27.0 | current_pack | pocket-loop-export-handoff | ERROR | — | — | — | — | — | sonnet |
| after-v0.28.0 | current_pack | coauthor-executable-policy-readback | FAIL | 14/15 | 33 | 29 | 69452 | 3.56 | sonnet |
| after-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 5323 | 0.36 | sonnet |
| after-v0.28.0 | current_pack | pocket-loop-export-handoff | ERROR | — | — | — | — | — | sonnet |
| after-v0.28.0 | current_pack | coauthor-executable-policy-readback | FAIL | 13/15 | 96 | 92 | 96275 | 9.39 | sonnet |
| after-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 7 | 5 | 12200 | 0.60 | sonnet |
| after-v0.28.0 | current_pack | pocket-loop-export-handoff | ERROR | — | — | — | — | — | sonnet |
| after-v0.28.0 | current_pack | coauthor-executable-policy-readback | FAIL | 12/15 | 26 | 22 | 68390 | 3.14 | sonnet |
| after-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 4079 | 0.33 | sonnet |
| after-v0.28.0 | current_pack | pocket-loop-export-handoff | ERROR | — | — | — | — | — | sonnet |

Notes: ARMS. before = c03ca60 (this branch's merge base, v0.27.0 — the last commit before the design note and the implementation); after = the worktree-ir-spec working tree at v0.28.0. HARNESS IDENTICAL: evals/run.py, evals/eval_backends.py and evals/benchmark_record.py were copied from the branch into the before worktree, and so were all three scenario directories, so both arms ran the same runner and were judged against byte-identical prompt.md / checks.json / deterministic-checker text. N=3 per arm; agent sonnet, judge opus, default efforts. NO CELL FLIPPED VERDICT — every coauthor-* cell is FAIL in both arms, because each scenario's check list contains at least one check that fails on both sides. The movement is inside the check counts and the deterministic checker, and that is all this entry claims. SCOPE, STATED FIRST: pocket-loop-export-handoff produced NO signal in either arm. It ERRORs at 'pocket preflight failed' in all 6 runs because this container has no nxd-desktop-supervisor binary; the preflight is memoized per runner process, so the other two cells still ran. That is infrastructure, identical on both sides, and it means the one scenario that exercises the export handoff end to end — the surface this change most directly rewrites — is UNBENCHMARKED. Anyone re-running should do so on a host with the supervisor. WHAT MOVED. coauthor-supplied-rubric deterministic check: 1/3 passed before, 3/3 after. Both before-arm failures are the ORDERING rule ('pre-build:proposes verdict mapping: no evidence before any materialization', first write at trace lines 112 and 113), not a missing-file failure — the before arm wrote its plan out before the read-back reached the user. Judge checks on that scenario: policy-will-land-as-data 3/3 fail before, 0/3 after; readback-before-any-write 2/3 fail before, 0/3 after; proposes-verdict-mapping 1/3 before, 0/3 after. THE ONE REGRESSION: provenance-addressed 0/3 fail before, 2/3 fail AFTER — the after arm twice omitted the 'LISTED - URL NOT CAPTURED' provenance handling from the read-back. That is a real move in the wrong direction, in the same scenario the rest of this paragraph improves, and at N=3 nothing here distinguishes a rewrite that crowded it out from noise. coauthor-executable-policy-readback: 13/15, 13/15, 12/15 before vs 14/15, 13/15, 12/15 after; deterministic 0/3 in both arms; edit-lands-as-editable-data 2/3 fail before vs 1/3 after; card-precedes-materialization 1/3 in both; flags-unreachable-c5-bottom-band fails 3/3 in BOTH arms — pre-existing, and untouched by this change. CONFOUND I EXPECTED AND DID NOT FIND: the copied-in checkers assert the NEW closure contract (dp-spec.approved.md), so the before arm could have failed by construction. It did not separate the arms — 'missing dp-spec.approved.md' fired exactly once per arm (before-1, after-1), because these scenarios stop at the read-back and mostly never build a closure at all, so that file-presence check is reached rarely and symmetrically. The before arm's other deterministic failures are one ordering failure and one INFRASTRUCTURE failure (before-2: uv could not fetch duckdb from PyPI, 'invalid peer certificate: UnknownIssuer' — the same proxy fault this ledger's 2026-05 entry records; it cost that cell its deterministic verdict and nothing else). EFFICIENCY, and it is not free: coauthor-executable-policy-readback output tokens went 41478/46823/83001 (mean 57.1k) to 69452/96275/68390 (mean 78.0k), +37%, with cost 2.20/2.45/5.16 to 3.56/9.39/3.14. Turns went 22/28/52 to 33/96/26 — the 96-turn run is a single outlier and the medians (28 vs 33) are close, but the token rise holds across all three after runs, so the richer closure contract does cost more agent work on the scenario that actually builds one. coauthor-supplied-rubric went the other way: 8716/22438/21521 (mean 17.6k) to 5323/12200/4079 (mean 7.2k), turns 6/12/13 to 6/7/6. Per evals/README, single-run metric deltas under ~20% are noise; at N=3 with one outlier per arm, read the check counts as the finding and the token figures as a direction, not a measurement. SCOPE OF THE CODE CHANGE MEASURED HERE: the arms differ by the whole spec-authoritative change set, not by the validator crash fix alone — validate_dp_spec.py's split-frontmatter drift (a raw traceback on unparseable frontmatter) is fixed in the after arm but is not on any path these scenarios exercise, so no row here measures it; evals/tests/test_validator_code_coverage.py and test_build_record_s0_producer.py do.

Record: [`records/2026-07-31-spec-authoritative-closures-context-md-retired-for-a-byte-co.json`](records/2026-07-31-spec-authoritative-closures-context-md-retired-for-a-byte-co.json)

## 2026-08-01 — nxd-pocket-loop / nxd-generate-dp: explicit built-in Desktop subagent dispatch (plugin v0.29.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| desktop-synthetic-probe | disposable synthetic skill | desktop-subagent-probe:run-probe | OBSERVED | 1/1 | — | — | — | — | Claude Desktop built-in Explore |

Notes: Observational evidence, not a `run.py` before/after benchmark. A disposable synthetic skill containing explicit built-in-subagent dispatch prose — and **no** custom/plugin agent definition — was invoked in Claude Desktop. Desktop visibly dispatched one built-in Explore subagent and returned the requested synthetic JSON. This establishes one instruction-following dispatch path only. It makes **no** correctness, latency, token, cost, review-quality, cancellation, deadline-persistence, or multi-question governed-query availability conclusion; the shipped source-contract tests cover the intended boundaries, and a full production closure Desktop E2E remains required.

Record: [`records/2026-08-01-explicit-built-in-desktop-subagent-dispatch.json`](records/2026-08-01-explicit-built-in-desktop-subagent-dispatch.json)

## 2026-07-31 — pocket-loop: non-capture sentinel routed to gate unknown (N=10/arm re-test of the reported provenance regression) (plugin v0.28.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.27.0 | current_pack | coauthor-supplied-rubric | FAIL | 7/12 | 13 | 11 | 19346 | 0.93 | sonnet |
| before-v0.27.0 | current_pack | coauthor-supplied-rubric | FAIL | 10/12 | 11 | 9 | 15555 | 0.81 | sonnet |
| before-v0.27.0 | current_pack | coauthor-supplied-rubric | PASS | 12/12 | 6 | 4 | 6991 | 0.40 | sonnet |
| before-v0.27.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 10961 | 0.47 | sonnet |
| before-v0.27.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 6965 | 0.40 | sonnet |
| before-v0.27.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 5152 | 0.37 | sonnet |
| before-v0.27.0 | current_pack | coauthor-supplied-rubric | FAIL | 10/12 | 15 | 13 | 15844 | 0.90 | sonnet |
| before-v0.27.0 | current_pack | coauthor-supplied-rubric | FAIL | 10/12 | 11 | 9 | 27055 | 1.06 | sonnet |
| before-v0.27.0 | current_pack | coauthor-supplied-rubric | PASS | 12/12 | 6 | 4 | 6830 | 0.40 | sonnet |
| before-v0.27.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 9105 | 0.44 | sonnet |
| after-v0.28.0 | current_pack | coauthor-supplied-rubric | PASS | 12/12 | 6 | 4 | 7237 | 0.40 | sonnet |
| after-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 9871 | 0.45 | sonnet |
| after-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 7 | 5 | 9234 | 0.50 | sonnet |
| after-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 8 | 6 | 8393 | 0.55 | sonnet |
| after-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 10/12 | 10 | 8 | 18628 | 0.90 | sonnet |
| after-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 9/12 | 9 | 7 | 8342 | 0.61 | sonnet |
| after-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 7 | 5 | 8619 | 0.43 | sonnet |
| after-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 9897 | 0.46 | sonnet |
| after-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 10/12 | 13 | 11 | 15501 | 0.83 | sonnet |
| after-v0.28.0 | current_pack | coauthor-supplied-rubric | PASS | 12/12 | 6 | 4 | 8153 | 0.43 | sonnet |
| fixed-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 6208 | 0.39 | sonnet |
| fixed-v0.28.0 | current_pack | coauthor-supplied-rubric | PASS | 12/12 | 6 | 4 | 5917 | 0.38 | sonnet |
| fixed-v0.28.0 | current_pack | coauthor-supplied-rubric | PASS | 12/12 | 6 | 4 | 9543 | 0.44 | sonnet |
| fixed-v0.28.0 | current_pack | coauthor-supplied-rubric | PASS | 12/12 | 6 | 4 | 7229 | 0.42 | sonnet |
| fixed-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 6615 | 0.41 | sonnet |
| fixed-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 10/12 | 10 | 8 | 17139 | 0.85 | sonnet |
| fixed-v0.28.0 | current_pack | coauthor-supplied-rubric | PASS | 12/12 | 6 | 4 | 8973 | 0.44 | sonnet |
| fixed-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 7 | 5 | 9109 | 0.47 | sonnet |
| fixed-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 7258 | 0.40 | sonnet |
| fixed-v0.28.0 | current_pack | coauthor-supplied-rubric | FAIL | 11/12 | 6 | 4 | 9003 | 0.43 | sonnet |

Notes: PURPOSE: settle the provenance-addressed regression the 2026-07-31 N=3 entry flagged as the top open item, then measure a fix. THREE ARMS, N=10 EACH, same scenario coauthor-supplied-rubric, agent sonnet / judge opus, identical harness: run.py, eval_backends.py, benchmark_record.py, skill-sets.yaml and the whole coauthor-supplied-rubric directory were copied from this branch into a detached c03ca60 worktree, verified byte-identical with diff -r, so the arms differ only in src/ skills. before-v0.27.0 = c03ca60. after-v0.28.0 = this branch before today's edit. fixed-v0.28.0 = after + the sentinel guidance. HEADLINE, AND IT IS NEGATIVE: THE REPORTED REGRESSION WAS AN ARTIFACT OF N=3. provenance-addressed fails 3/10 in the before arm, not the 0/3 the prior entry recorded; its true rate was always about a third and the original three samples happened to draw three passes. before 3/10 vs after 5/10 gives Fisher exact p=0.65 — no regression is demonstrable, and the prior entry's own caveat that N=3 could not separate signal from noise was correct. THE FIX AND WHAT IT IS WORTH: the failures are one repeated semantic error, not a formatting miss — the agent collapses evidence-not-captured into evidence-absent, routing the literal string LISTED - URL NOT CAPTURED to a hard G1 FAIL instead of UNKNOWN, and in one run chaining it to REJECT, overriding the user's own stated NEEDS_MORE_INFO cap. The scenario prompt states that cap explicitly, so those runs contradict a user instruction. Guidance was added in two places (reference/dp-spec.md gates section, SKILL.md Step 1b) telling the agent that a present non-empty sentinel encoding non-capture is an unknown, not a failing value. after 5/10 vs fixed 3/10, p=0.65: DIRECTIONALLY BETTER, NOT DEMONSTRATED. At an interim N=9 the fixed arm read 2/9 and looked stronger; the tenth run moved it to 3/10, which is exactly the instability this entry exists to warn about. Do not cite this fix as proven. WHY IT SHIPS ANYWAY: the validator already rejects unknown: FAIL via spec.gate.unknown_is_fail, so a spec cannot declare the wrong rule — but it cannot tell that LISTED - URL NOT CAPTURED means uncaptured, so a spec that misclassifies a sentinel validates clean and is still wrong. The gap is real and mechanically uncatchable whatever the eval says; the measurement only fails to prove the prose closes it. WHAT ELSE MOVED, unprompted by the fix: unknown-gate-addressed fails 4/10 before and 0/10 after — a genuine v0.28.0 improvement the N=3 entry missed entirely. Overall PASS count 2/10 before, 2/10 after, 4/10 fixed. Efficiency on this scenario went the right way: mean output tokens 12380 before, 10388 after, 8699 fixed; mean turns 8.6 / 7.8 / 6.5. STILL FAILING AND NOT ADDRESSED HERE: readback-before-any-write 4/10 before, 4/10 after, 2/10 fixed — a gate-ordering rule, invisible at N=3 (0/3), and its own investigation. SCOPE: this entry measures one scenario. pocket-loop-export-handoff remains UNBENCHMARKED — it still ERRORs at pocket preflight with no nxd-desktop-supervisor in this container, and stages s4-s8 remain unexecuted against a real supervisor.

Record: [`records/2026-07-31-pocket-loop-non-capture-sentinel-routed-to-gate-unknown-n-10.json`](records/2026-07-31-pocket-loop-non-capture-sentinel-routed-to-gate-unknown-n-10.json)

## 2026-08-02 — closure-contract eval retargets: runtime observations in build records (rubric alignment, plugin v0.29.0)

**No before/after run table — rubric drift, not a measured skill change.**
`worldbank-live`'s `context-discloses-as-of-fetch` now distinguishes stable
live-source scope from fetch-specific runtime evidence:
`dp-spec.approved.md` must say that the data is a live-source snapshot and that
rebuilds can revise it, while the observed upstream `lastupdated` must appear
in `build-record.json` under `evidence.source_state`. This prevents a timestamp
from one fetch being frozen into the approved plan. The same CONTEXT.md
retirement retargets `treasury-yield-curve`'s closure file-set check and the
three `country-income-trajectory` disclosure checks
(`year-subset-selection-disclosed`, `aggregate-exclusion-ruling-landed`, and
`current-classification-scope-disclosed`) to the approved-spec / generated-
record closure contract. Those vendored-source checks have no runtime
`lastupdated` observation: their source or analysis scope remains plan content,
while generated build outcomes remain in `build-record.json`. These changes
narrow or relocate accepted closure shapes, so historical and future runs are
not judged by byte-identical rubric text.

No live evaluation was run. `worldbank-live`, `treasury-yield-curve`, and
`country-income-trajectory` are `ci_skip` because they require a live desktop
supervisor; World Bank additionally needs outbound access to
`api.worldbank.org`. This environment has neither `EVAL_POCKET_SUPERVISOR_DIR`
nor `EVAL_POCKET_PYTHON`, and `nxd-desktop-supervisor` is absent. The static
regression test pins the prompt/checker boundary only. It establishes no
PASS/FAIL, quality, latency, token, cost, or runtime-connector claim.

## 2026-08-02 — pocket custom contracts rebased onto the spec-authoritative IR (plugin v0.30.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.29.0 | current_pack | coauthor-supplied-rubric | FAIL | 7/12 | — | 34 | 19426 | — | gpt-5.6-luna |
| before-v0.29.0 | current_pack | coauthor-supplied-rubric | FAIL | 2/12 | — | 7 | 3509 | — | gpt-5.6-luna |
| before-v0.29.0 | current_pack | coauthor-supplied-rubric | FAIL | 5/12 | — | 17 | 16093 | — | gpt-5.6-luna |
| after-v0.30.0 | current_pack | coauthor-supplied-rubric | FAIL | 2/12 | — | 20 | 15766 | — | gpt-5.6-luna |
| after-v0.30.0 | current_pack | coauthor-supplied-rubric | FAIL | 4/12 | — | 27 | 28095 | — | gpt-5.6-luna |
| after-v0.30.0 | current_pack | coauthor-supplied-rubric | FAIL | 5/12 | — | 34 | 3496 | — | gpt-5.6-luna |

Notes: **No difference is demonstrable, and no Pocket-contract claim is made here.** Scenario `coauthor-supplied-rubric`, N=3 per arm, agent AND judge on the codex backend, same harness and rubric in both arms. Arms differ only in `src/`: the before arm is a clean worktree at origin/main (446369f), the after arm is this branch. `build_agent_prompt` was verified to emit a BYTE-IDENTICAL prompt across the two arms for a non-isolated scenario, so the source-isolation harness this branch also carries does not confound the comparison.

Judge checks: before 7/2/5 (mean 4.7/12), after 2/4/5 (mean 3.7/12). Two-sided exact permutation test on the difference of means: **p=0.80**. Every per-check difference is a single run out of three and none flips consistently, so the apparent 1-check drop is noise at this N, not a regression. The deterministic check is **1/3 in BOTH arms**, failing identically (`pre-build:names the incomplete scale: no evidence before any materialization`). Output tokens 13.0k vs 15.8k mean, which at this N and this variance (3.5k-28.1k within a single arm) says nothing.

**What this run does NOT cover.** `pocket-custom-contracts` — the scenario that exercises the contract work this PR is about — is not measured here. **It has since been run: see the source-isolated entry below, which is the authoritative evidence for this change.** At the time of this run it failed closed without an operator-supplied default-deny wrapper, capability ID, 64-hex profile fingerprint and five protected roots. It errors with `source-isolation infrastructure invalid: missing source-isolation capability ID` rather than degrading to an unisolated run, which is the harness behaving correctly. The three v0.27.0 entries above measured the PRE-REBASE implementation of this work — a different Phase C gate, a CONTEXT.md-based inventory, and no dp-spec IR sections. **Do not read them as evidence for this branch.** The contract behaviour here is covered by 37 checker tests and a 460-test suite, not by an eval arm.

Record: [`records/2026-08-02-pocket-custom-contracts-rebased-onto-the-spec-authoritative-.json`](records/2026-08-02-pocket-custom-contracts-rebased-onto-the-spec-authoritative-.json)

## 2026-08-02 — executable Pocket custom contracts, source-isolated (pocket-custom-contracts) (plugin v0.30.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.29.0 | current_pack | pocket-custom-contracts | FAIL | 0/5 | — | 17 | 13693 | — | gpt-5.6-luna |
| before-v0.29.0 | current_pack | pocket-custom-contracts | FAIL | 0/5 | — | 1 | 1102 | — | gpt-5.6-luna |
| before-v0.29.0 | current_pack | pocket-custom-contracts | FAIL | 0/5 | — | 14 | 8956 | — | gpt-5.6-luna |
| after-v0.30.0 | current_pack | pocket-custom-contracts | PASS | 5/5 | — | 26 | 12830 | — | gpt-5.6-luna |
| after-v0.30.0 | current_pack | pocket-custom-contracts | PASS | 5/5 | — | 24 | 13254 | — | gpt-5.6-luna |
| after-v0.30.0 | current_pack | pocket-custom-contracts | PASS | 5/5 | — | 22 | 11490 | — | gpt-5.6-luna |
| after-v0.30.0 | current_pack | pocket-custom-contracts | FAIL | 4/5 | — | 15 | 8031 | — | gpt-5.6-luna |

Notes: **The scenario this PR exists for now runs, and it separates cleanly.** `pocket-custom-contracts`, source-isolated, agent AND judge on the codex backend (gpt-5.6-luna). Before arm = this branch's harness and scenario with `src/` at origin/main (446369f); after arm = this branch. main does not carry this scenario at all — it ships with this PR — so the before arm necessarily supplies the scenario and varies only the skills, which is the same framing the retracted v0.27.0 isolated entry used.

Judge checks: before **0/5, 0/5, 0/5**; after **5/5, 5/5, 5/5, 4/5** (mean 4.75/5). The deterministic checker goes **0/3 to 4/4**. Fisher exact, two-sided, on both any-check-passed and the deterministic checker: **p=0.029**. Every one of the five checks improves; none regresses.

The before-arm failures are exactly what this change adds, not incidental noise — `FAIL infra-profile.yaml lacks the desktop-local DuckDB, compute, and csv-source services; FAIL custom description missing; FAIL custom verifier must u[se ...]`. Without the skill guidance the agent does not produce wired executable contracts at all.

**Isolation evidence.** All 7 default-deny probes reported `blocked` on every run, wrapper path and sha256 identical across arms, raw-stream audit `clean` on all reported runs. Enforcement is macOS `sandbox-exec`, so the denial is kernel-level rather than advisory. The probe requires the kernel's denial signature rather than a mere non-zero exit — a malformed Seatbelt policy fails WITHOUT enforcing, and reading that as "blocked" would attest isolation that never applied; it reports `sandbox-error` instead. These runs were re-verified 7/7 under that stricter check.

**One after-run was DISCARDED and is not in the table.** Its audit returned `access_observed` for five markers. The isolation held — all 7 probes still blocked — but a `root` marker's needle IS the protected path, and a *denied* access still prints that path (`ls: /path: Operation not permitted`), so an attempt that the sandbox correctly refused is indistinguishable from one that succeeded. The harness fails the run rather than guess, which is the right call; it was replaced rather than reinterpreted. After-arm n=4, not 5, because two runs collided on one report filename — the surviving file is one of them, not a merge.

Efficiency is not compared: the before arm never produces a working closure, so its token and tool counts measure failing early, not doing the work more cheaply.

Record: [`records/2026-08-02-executable-pocket-custom-contracts-source-isolated-pocket-cu.json`](records/2026-08-02-executable-pocket-custom-contracts-source-isolated-pocket-cu.json)

## 2026-08-02 — validate_dp_spec: duplicate-contract diagnostics field-addressed (plugin v0.30.1)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | — | — |

Notes: **No eval arm, deliberately, and no behaviour claim is made from one.**
This entry exists because `src/nxd-pocket-loop/scripts/validate_dp_spec.py` is
shipped skill code and its OUTPUT changed — `spec.contract.duplicate_name` moves
from `path: spec:expectations` to `spec:<section>[<name>].name`, its message no
longer names a section the document may not contain, and a same-section
collision emits one finding rather than one per colliding entry. A pocket-loop
agent reads those fields, so the change is not invisible even though no closure
it generates changes.

It is not benchmarkable: no public scenario authors a spec with a duplicate
contract name, so every arm would be byte-identical and the comparison would
measure nothing. Manufacturing a scenario to produce a number for a diagnostic
bugfix would make the ledger less honest, not more. The evidence is four unit
tests in `evals/tests/test_validator_code_coverage.py` and
`test_pocket_custom_contract_checker.py`, each **verified to fail against the
previous implementation** rather than assumed to — including the secret-regex
parity test, which parses `SECRET_LITERAL` out of `scripts/self_check.py` and
compares compiled patterns, so the eval checker and Phase C cannot drift again.

Recorded per AGENTS.md's "changes a skill's behavior" rule, read strictly. The
v0.30.0 entry above makes the same argument for the contract work itself —
coverage resting on the test suite rather than on an eval arm — and this is the
narrower case of it.
