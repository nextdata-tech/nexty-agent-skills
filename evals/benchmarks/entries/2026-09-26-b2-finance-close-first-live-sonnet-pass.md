---
id: "2026-09-26-b2-finance-close-first-live-sonnet-pass"
date: "2026-09-26"
label: "B2 finance-close first live Sonnet pass"
plugin_version: "0.53.1"
status: "MIXED"
scenarios:
  - "finance-close"
record: "../records/2026-09-26-b2-finance-close-first-live-sonnet-pass.json"
---
# Benchmark — B2 finance-close first live Sonnet pass

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-run14 | dp-scenarios | finance-close | PASS | 4/4 | 14 | 190 | — | — | claude:sonnet |
| after-run15 | dp-scenarios | finance-close | FAIL | 1/4 | 14 | 259 | — | — | claude:sonnet |

## Notes

Two live Claude Sonnet runs of B2 finance-close on identical code (the #344 branch c37dd3b4, squash-merged to main as c275ec96) with the same pinned supervisor and session config. The before/after tags only satisfy the pairing rule: no code changed between the arms, so this measures run-to-run variance, not a change. Run 14 passed clean: 55, with intake, construction, build and follow-up passing, replay verified, QUALIFIED; it is B2's first live pass. Run 15 passed intake but never published a build (construction_published_build_missing): the agent kept opening further robustness review rounds, and the scripted operator stopped authorising them once review-fix approval asks were classified as generic approval requests and one was captured by the weekend-FX decision answer. That operator routing gap is being fixed separately. One pass in two same-code epochs demonstrates a pass once and gives no repeatability rate.

## Evidence

Compact report: [`../records/2026-09-26-b2-finance-close-first-live-sonnet-pass.json`](../records/2026-09-26-b2-finance-close-first-live-sonnet-pass.json)
