---
id: "2026-09-24-b3-marketing-attribution-first-live-sonnet-pass"
date: "2026-09-24"
label: "B3 marketing-attribution first live Sonnet pass"
plugin_version: "0.52.9"
status: "MIXED"
scenarios:
  - "marketing-attribution"
record: "../records/2026-09-24-b3-marketing-attribution-first-live-sonnet-pass.json"
---
# Benchmark — B3 marketing-attribution first live Sonnet pass

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| run12 | dp-scenarios | marketing-attribution | FAIL | 3/4 | 10 | 126 | — | — | claude:sonnet |
| run13 | dp-scenarios | marketing-attribution | PASS | 4/4 | 10 | 247 | — | — | claude:sonnet |

## Notes

Live Claude Sonnet runs of B3 marketing-attribution on skills 0.52.8 (main with #322-#324; recorded after 0.52.9 merged) and a supervisor built from nxd main (with nxd#7951/#7953). Run 13 passed clean: 45 against a threshold of 36; intake, construction, build and follow-up pass; the sentinel scan was examined and clean; replay verified; QUALIFIED. Run 12 on identical code failed only intake: after rejected prepares the agent fixed the inline typed proposal but did not write the fix back to dp-blueprint.proposal.json. One pass in two same-code epochs is demonstrated-once, not a repeatability rate.

## Evidence

Compact report: [`../records/2026-09-24-b3-marketing-attribution-first-live-sonnet-pass.json`](../records/2026-09-24-b3-marketing-attribution-first-live-sonnet-pass.json)
