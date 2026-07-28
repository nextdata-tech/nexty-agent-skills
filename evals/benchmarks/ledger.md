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
