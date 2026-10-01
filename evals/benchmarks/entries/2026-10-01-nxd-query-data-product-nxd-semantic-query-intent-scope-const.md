---
id: "2026-10-01-nxd-query-data-product-nxd-semantic-query-intent-scope-const"
date: "2026-10-01"
label: "nxd-query-data-product / nxd-semantic-query-intent: scope constraints become filters (#442)"
plugin_version: "0.54.10"
status: "MIXED"
scenarios:
  - "semantic-filter-coverage"
  - "semantic-intent-validation"
record: "../records/2026-10-01-nxd-query-data-product-nxd-semantic-query-intent-scope-const.json"
---
# Benchmark — nxd-query-data-product / nxd-semantic-query-intent: scope constraints become filters (#442)

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-sfc-r1 | current_pack | semantic-filter-coverage | PASS | 7/7 | 15 | 13 | 5544 | 0.43 | sonnet |
| before-sfc-r2 | current_pack | semantic-filter-coverage | PASS | 7/7 | 16 | 14 | 5743 | 0.44 | sonnet |
| before-sfc-r3 | current_pack | semantic-filter-coverage | PASS | 7/7 | 14 | 12 | 6179 | 0.44 | sonnet |
| after-sfc-r1 | current_pack | semantic-filter-coverage | PASS | 7/7 | 15 | 13 | 5978 | 0.44 | sonnet |
| after-sfc-r2 | current_pack | semantic-filter-coverage | PASS | 7/7 | 16 | 14 | 6100 | 0.39 | sonnet |
| after-sfc-r3 | current_pack | semantic-filter-coverage | PASS | 7/7 | 15 | 13 | 6249 | 0.53 | sonnet |
| before-siv-r1 | current_pack | semantic-intent-validation | FAIL | 8/9 | 20 | 17 | 5866 | 0.49 | sonnet |
| before-siv-r2 | current_pack | semantic-intent-validation | FAIL | 2/9 | 15 | 12 | 2656 | 0.34 | sonnet |
| before-siv-r3 | current_pack | semantic-intent-validation | FAIL | 2/9 | 11 | 9 | 2042 | 0.24 | sonnet |
| before-siv-r2-retry | current_pack | semantic-intent-validation | FAIL | 2/9 | 13 | 10 | 2320 | 0.32 | sonnet |
| before-siv-r3-retry | current_pack | semantic-intent-validation | FAIL | 8/9 | 21 | 18 | 6148 | 0.58 | sonnet |
| after-siv-r1 | current_pack | semantic-intent-validation | PASS | 9/9 | 19 | 17 | 6705 | 0.46 | sonnet |
| after-siv-r2 | current_pack | semantic-intent-validation | FAIL | 8/9 | 22 | 19 | 6599 | 0.58 | sonnet |
| after-siv-r3 | current_pack | semantic-intent-validation | FAIL | 8/9 | 21 | 19 | 6017 | 0.52 | sonnet |

## Notes

NEX-1244: a customer eval showed agents dropping scope filters (region, specialty, product) from governed semantic queries; #442 makes every question constraint a semantic filter, separates scope filters from breakdowns, probes stored values before reporting a zero, and carves out metrics that already encode the constraint (partner_sourced_revenue). Two scenarios, Sonnet agent at high effort, 3 runs per arm, local mesh at nxd df96ee66 / nxd_data_product 0.41.246, scenarios and harness from PR #445 (branch claude/local-mesh-filter-evals). (1) semantic-filter-coverage: both arms ran with one extra prompt line telling the agent to follow the installed nxd-query-data-product skill (without it Sonnet never invoked the skill in 3/3 runs and the cell failed on missing tools; those pre-cue runs, before-sfc-1b.json and probe-medium.json, are excluded). Result 7/7 in all 6 runs: a ceiling effect, because Sonnet with the skills already kept the filters and probed values before reporting the Q4 zero on main, so the scenario does not distinguish the arms; efficiency is flat. (2) semantic-intent-validation, the Q3 partner-trap regression guard, run against scratch Snowflake schema EVAL_BENCH_442 (created and dropped for the run). AFTER = #445 HEAD as is (includes #442). BEFORE = same tree with #442's documentation reverted to 001afdd5 (staged, never committed), keeping scripts/ and the #445 harness: src/nxd-query-data-product/SKILL.md, src/nxd-query-data-product/README.md, src/nxd-query-data-product/reference/troubleshooting.md, src/nxd-semantic-query-intent/SKILL.md, src/nxd-semantic-query-intent/reference/semantic-intent-validation.md, src/nxd-run-job-loop/SKILL.md, src/nxd-run-job-loop/reference/query-grammar.md, src/nxd-build-semantic-data-product/reference/compiler-and-routing.md (metadata.version lines in the reverted files went back with them). Partner trap: AFTER chose partner_sourced_revenue (275, not 150) in 3/3 runs. BEFORE chose it in 1/5 runs (before-r3-retry), over-clarified instead of executing in 1 (before-r1), and in 3 runs (r2, r3, r2-retry) never reached the semantic tools at all: the agent searched deferred tools, declined to use the local mesh, and stopped, so those runs fail every check for lack of evidence about the skill. The two re-run rows (before-siv-r2-retry, before-siv-r3-retry) are retries of the two no-tool runs; they are kept alongside the originals, not substituted. Tool reach is 3/3 AFTER vs 2/5 BEFORE, but n is small and the reverted text does not touch mesh discovery, so treat it as suggestive, not attributed to #442. Separately, echo-produced failed in 2/3 AFTER and 1 of the 2 BEFORE runs that reached tools (the echo came only in the final answer, after execution). Efficiency per run is similar when tools are reached (about 19-22 turns, 0.46-0.58 USD). The semantic-intent-validation runs used PR #445's fake mesh gateway at 63e28fe4, whose proxy__get_data_product_details returned a flatter shape than the production proxy (a later #445 commit matches it); both arms share that harness, so the comparison is arm-to-arm, not a claim about the production details response.

## Evidence

Compact report: [`../records/2026-10-01-nxd-query-data-product-nxd-semantic-query-intent-scope-const.json`](../records/2026-10-01-nxd-query-data-product-nxd-semantic-query-intent-scope-const.json)
