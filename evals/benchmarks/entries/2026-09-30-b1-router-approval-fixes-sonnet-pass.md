---
id: "2026-09-30-b1-router-approval-fixes-sonnet-pass"
date: "2026-09-30"
label: "dp-scenarios operator: clarify-once approval and router rules (#430), B1 live Sonnet pass"
plugin_version: "0.54.8"
status: "MIXED"
scenarios:
  - "crm-pipeline"
record: "../records/2026-09-30-b1-router-approval-fixes-sonnet-pass.json"
---
# Benchmark — dp-scenarios operator: clarify-once approval and router rules (#430), B1 live Sonnet pass

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before | dp-scenarios | crm-pipeline | ERROR | 5/5 | 24 | 437 | — | — | claude:sonnet |
| after | dp-scenarios | crm-pipeline | PASS | 5/5 | 24 | 475 | — | — | claude:sonnet |

## Notes

Same pinned supervisor, Claude Sonnet high, --operator-router llm (codex gpt-6.1-sol, medium). Before: router1 at 7fc95f9c, UNGRADED 70 (all gates passed but the turn budget ran out while approval asks got persona replies). After: router2 at 1c0b5571 (#430, plus #427-#429) clean PASS 70; 24 replies routed by the model, 0 fallbacks. Only the router prompt hash differs between arms. One run per arm; no repeatability rate.

## Evidence

Compact report: [`../records/2026-09-30-b1-router-approval-fixes-sonnet-pass.json`](../records/2026-09-30-b1-router-approval-fixes-sonnet-pass.json)
