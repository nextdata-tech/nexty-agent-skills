---
id: "2026-09-09-b-series-genuine-completion"
date: "2026-09-09"
label: "b-series: genuine completion workflow"
plugin_version: "0.46.0"
status: "FAIL"
scenarios:
  - "crm-pipeline"
  - "finance-close"
  - "inventory-position"
record: "../records/2026-09-09-b-series-genuine-completion.json"
---
# Benchmark — b-series: genuine completion workflow

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-0.45.1 | dp-scenarios | crm-pipeline | FAIL | 4/5 | 11 | 108 | — | — | sonnet |
| before-0.45.1 | dp-scenarios | finance-close | FAIL | 3/4 | 8 | 90 | — | — | sonnet |
| before-0.45.1 | dp-scenarios | inventory-position | FAIL | 2/4 | 9 | 106 | — | — | sonnet |
| after-0.46.0 | dp-scenarios | crm-pipeline | FAIL | 4/5 | 11 | 108 | — | — | sonnet |
| after-0.46.0 | dp-scenarios | finance-close | FAIL | 3/4 | 8 | 76 | — | — | sonnet |
| after-0.46.0 | dp-scenarios | inventory-position | FAIL | 2/4 | 9 | 112 | — | — | sonnet |

## Notes

Both arms completed normally against the same final harness and rebuilt supervisor. The 0.46.0 skill changes produced no score or gate improvement: B1/B2/B5 still failed construction, and B5 also failed approval-before-codegen.

## Evidence

Compact report: [`../records/2026-09-09-b-series-genuine-completion.json`](../records/2026-09-09-b-series-genuine-completion.json)
