---
id: "2026-10-03-nex-1244-filter-eval-baseline-nxd-0-41-246"
date: "2026-10-03"
label: "NEX-1244 filter-coverage baseline on nxd 0.41.246 (same-pin, current main skills)"
plugin_version: "0.54.15"
status: "PASS"
scenarios:
  - "semantic-filter-coverage"
record: "../records/2026-10-03-nex-1244-filter-eval-baseline-nxd-0-41-246.json"
---
# Benchmark — NEX-1244 filter-coverage baseline on nxd 0.41.246 (same-pin, current main skills)

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| baseline-1 | current_pack | semantic-filter-coverage | PASS | 7/7 | 17 | 15 | 6726 | 0.56 | sonnet |
| baseline-2 | current_pack | semantic-filter-coverage | PASS | 7/7 | 18 | 16 | 6488 | 0.61 | sonnet |
| baseline-3 | current_pack | semantic-filter-coverage | PASS | 7/7 | 16 | 14 | 6431 | 0.55 | sonnet |

## Notes

Same-pin baseline, not a before/after pair: current main skills (40307453) on nxd core 0.41.246 and data_product 0.41.247, no skill change under test. Primary (nxd_eval filter_coverage, openai/gpt-6-luna, arm B, 5 epochs, --isolate): 20/20, 731,392 total tokens (711,685 in of which 648,546 cached, 19,707 out); dollar cost not computed (no price table). Secondary (public semantic-filter-coverage, Sonnet, high effort, 3 runs): 3/3 at 7/7 checks; cost 0.56+0.61+0.55 = about 1.72 USD. Both evals are at the ceiling, so they cannot distinguish nxd v0.41.248/v0.41.250 (#8141 top-25 stored values with the completeness flag, #8139 distinct-count final-grain route and NULL-bucket gate). The v0.41.250 runs were not done: they need a swap of the local mesh pip-registry image that the user declined. Comparison points: #451 arm B (16/20 -> 20/20) and the 2026-10-02 Sonnet entry (2/3 passes in each arm).

## Evidence

Compact report: [`../records/2026-10-03-nex-1244-filter-eval-baseline-nxd-0-41-246.json`](../records/2026-10-03-nex-1244-filter-eval-baseline-nxd-0-41-246.json)
