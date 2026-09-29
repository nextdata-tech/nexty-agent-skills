---
id: "2026-09-29-b5-current-ask-routing-sonnet-pass"
date: "2026-09-29"
label: "dp-scenarios operator: route replies from the current ask (#400), B5 live Sonnet pass"
plugin_version: "0.54.4"
status: "PASS"
scenarios:
  - "inventory-position"
record: "../records/2026-09-29-b5-current-ask-routing-sonnet-pass.json"
---
# Benchmark — dp-scenarios operator: route replies from the current ask (#400), B5 live Sonnet pass

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before | dp-scenarios | inventory-position | PASS | 4/4 | 11 | 157 | — | — | claude:sonnet |
| after | dp-scenarios | inventory-position | PASS | 4/4 | 11 | 157 | — | — | claude:sonnet |

## Notes

Same pinned supervisor, Claude Sonnet high backend, scripted operator. Before: run4 at 8d4e5575 (#379) clean PASS 55; the intervening regression run regress1 at f53ec83f was UNGRADED (turn budget exhausted after a 'reply 1 or 2' review choice got a repeat-suppressed source answer) and cannot be scored. After: r400 at 334846ba (#400) clean PASS 55, restoring B5 on current main. One run per arm; no repeatability rate.

## Evidence

Compact report: [`../records/2026-09-29-b5-current-ask-routing-sonnet-pass.json`](../records/2026-09-29-b5-current-ask-routing-sonnet-pass.json)
