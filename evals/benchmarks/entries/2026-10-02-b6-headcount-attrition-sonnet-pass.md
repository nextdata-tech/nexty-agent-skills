---
id: "2026-10-02-b6-headcount-attrition-sonnet-pass"
date: "2026-10-02"
label: "B6 headcount-attrition: suppression, bare-affirmative and review-ruling fixes (#448-#456)"
plugin_version: "0.54.14"
status: "MIXED"
scenarios:
  - "headcount-attrition"
record: "../records/2026-10-02-b6-headcount-attrition-sonnet-pass.json"
---
# Benchmark — B6 headcount-attrition: suppression, bare-affirmative and review-ruling fixes (#448-#456)

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before | dp-scenarios | headcount-attrition | ERROR | 4/4 | 12 | 158 | — | — | claude:sonnet |
| after | dp-scenarios | headcount-attrition | PASS | 4/4 | 12 | 126 | — | — | claude:sonnet |

## Notes

Before: router10 (Sol router, after #448-#455) passed every scored gate but ended UNGRADED turn_budget_exhausted_pending_answer after turning advisory review notes into post-publication questions. After: router12 on main 15b8a62d (#456) PASS clean 45, completed. The after run used a Claude (sonnet medium) operator router because the Codex router quota was exhausted; router11 (Codex fallback) is excluded as invalid evidence.

## Evidence

Compact report: [`../records/2026-10-02-b6-headcount-attrition-sonnet-pass.json`](../records/2026-10-02-b6-headcount-attrition-sonnet-pass.json)
