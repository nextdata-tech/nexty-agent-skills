---
id: "2026-09-26-b5-inventory-position-first-live-sonnet-pass"
date: "2026-09-26"
label: "B5 inventory-position first live Sonnet pass"
plugin_version: "0.53.1"
status: "MIXED"
scenarios:
  - "inventory-position"
record: "../records/2026-09-26-b5-inventory-position-first-live-sonnet-pass.json"
---
# Benchmark — B5 inventory-position first live Sonnet pass

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-run9 | dp-scenarios | inventory-position | PASS | 4/4 | 11 | 237 | — | — | claude:sonnet |
| after-run10 | dp-scenarios | inventory-position | FAIL | 3/4 | 11 | 210 | — | — | claude:sonnet |

## Notes

Two live Claude Sonnet runs of B5 inventory-position on identical code (main 95e85763, after #338 and #341) with the same pinned supervisor and session config. The before/after tags only satisfy the pairing rule: no code changed between the arms, so this measures run-to-run variance, not a change. Run 9 passed clean: 55, with intake, construction, build and follow-up passing, replay verified, QUALIFIED. Run 10 passed intake, build and follow-up but failed construction with construction_review_round_invalid (a review-ledger round failed validation; the report does not surface which rule). Earlier failing runs on the #341 branch (7 and 8) were genuine agent contract slips: an unrecorded review user_decision, and an inline typed proposal that reworded the saved file's echo.text. One pass in two same-code epochs demonstrates a pass once and gives no repeatability rate.

## Evidence

Compact report: [`../records/2026-09-26-b5-inventory-position-first-live-sonnet-pass.json`](../records/2026-09-26-b5-inventory-position-first-live-sonnet-pass.json)
