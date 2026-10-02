---
id: "2026-10-02-filter-discipline-451-semantic-filter-coverage"
date: "2026-10-02"
label: "nxd-query-data-product + nxd-semantic-query-intent: unfiltered value probes, whole compound values, no unrequested filters (#451)"
plugin_version: "0.54.14"
status: "MIXED"
scenarios:
  - "semantic-filter-coverage"
record: "../records/2026-10-02-filter-discipline-451-semantic-filter-coverage.json"
---
# Benchmark — nxd-query-data-product + nxd-semantic-query-intent: unfiltered value probes, whole compound values, no unrequested filters (#451)

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before | current_pack | semantic-filter-coverage | FAIL | 6/7 | 13 | 11 | 4538 | 0.39 | sonnet |
| before | current_pack | semantic-filter-coverage | PASS | 7/7 | 16 | 14 | 4876 | 0.40 | sonnet |
| before | current_pack | semantic-filter-coverage | PASS | 7/7 | 15 | 13 | 4827 | 0.42 | sonnet |
| after | current_pack | semantic-filter-coverage | PASS | 7/7 | 12 | 10 | 4546 | 0.38 | sonnet |
| after | current_pack | semantic-filter-coverage | PASS | 7/7 | 15 | 13 | 4513 | 0.37 | sonnet |
| after | current_pack | semantic-filter-coverage | FAIL | 6/7 | 14 | 12 | 4031 | 0.36 | sonnet |

## Notes

Tightens filter discipline in the query and intent skills (unfiltered value probes, whole compound values, no unrequested filters). On the local-mesh semantic-filter-coverage scenario (Sonnet agent, 3 runs per arm, same mesh and nxd pin) both arms are indistinguishable: 2/3 passes each, with the only failing check being discovery-before-query (marker model not described) in one run per arm; the scenario does not discriminate the change on this model. The discriminating evidence is the nxd_eval gpt-6-luna arm-B result in PR #451 (16/20 -> 20/20).

## Evidence

Compact report: [`../records/2026-10-02-filter-discipline-451-semantic-filter-coverage.json`](../records/2026-10-02-filter-discipline-451-semantic-filter-coverage.json)
