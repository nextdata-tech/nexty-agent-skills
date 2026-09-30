---
id: "2026-09-30-b5-llm-router-sonnet-pass"
date: "2026-09-30"
label: "dp-scenarios operator: LLM router (#424, #430), B5 live Sonnet pass"
plugin_version: "0.54.8"
status: "PASS"
scenarios:
  - "inventory-position"
record: "../records/2026-09-30-b5-llm-router-sonnet-pass.json"
---
# Benchmark — dp-scenarios operator: LLM router (#424, #430), B5 live Sonnet pass

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before | dp-scenarios | inventory-position | PASS | 4/4 | 11 | 172 | — | — | claude:sonnet |
| after | dp-scenarios | inventory-position | PASS | 4/4 | 11 | 191 | — | — | claude:sonnet |

## Notes

Same pinned supervisor, Claude Sonnet high, --operator-router llm (codex gpt-6.1-sol, medium). Before: router1 at a39c2d7d (#424) clean PASS 55. After: router2 at 1c0b5571 (#430) clean PASS 55; 11 replies routed by the model in each arm, 0 fallbacks. B5 holds under the router across the operator fixes. Only the router prompt hash differs between arms. One run per arm; no repeatability rate.

## Evidence

Compact report: [`../records/2026-09-30-b5-llm-router-sonnet-pass.json`](../records/2026-09-30-b5-llm-router-sonnet-pass.json)
