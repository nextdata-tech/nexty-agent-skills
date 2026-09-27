---
id: "2026-09-26-b1-crm-pipeline-live-sonnet-pass-on-current-main"
date: "2026-09-26"
label: "B1 crm-pipeline live Sonnet pass on current main"
plugin_version: "0.53.1"
status: "PASS"
scenarios:
  - "crm-pipeline"
record: "../records/2026-09-26-b1-crm-pipeline-live-sonnet-pass-on-current-main.json"
---
# Benchmark — B1 crm-pipeline live Sonnet pass on current main

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-run1 | dp-scenarios | crm-pipeline | PASS | 5/5 | 22 | 554 | — | — | claude:sonnet |
| after-run2 | dp-scenarios | crm-pipeline | PASS | 5/5 | 22 | 378 | — | — | claude:sonnet |

## Notes

Two live Claude Sonnet runs of B1 crm-pipeline on identical code (main 95e85763, skills 0.53.1, after #338 and #341) with the same pinned supervisor and session config. The before/after tags only satisfy the pairing rule: no code changed between the arms. Both passed clean at 70, with intake, capability, construction, build and follow-up passing, replay verified and QUALIFIED. Two passes in two same-code epochs is a small sample, not a repeatability rate.

## Evidence

Compact report: [`../records/2026-09-26-b1-crm-pipeline-live-sonnet-pass-on-current-main.json`](../records/2026-09-26-b1-crm-pipeline-live-sonnet-pass-on-current-main.json)
