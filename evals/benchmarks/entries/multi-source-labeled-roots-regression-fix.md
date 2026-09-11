---
id: "multi-source-labeled-roots-regression-fix"
date: "2026-09-11"
label: "nxd-generate-data-product: multi-source labeled-root regression fix"
plugin_version: "0.49.2"
status: "PASS"
scenarios:
  - "multi-source-labeled-roots"
record: "../records/multi-source-labeled-roots-regression-fix.json"
---
# Benchmark — nxd-generate-data-product: multi-source labeled-root regression fix

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before | current_pack | multi-source-labeled-roots | PASS | 9/9 | — | 32 | 13981 | — | gpt-5.6-luna |
| after-final-1 | current_pack | multi-source-labeled-roots | PASS | 9/9 | — | 37 | 18733 | — | gpt-5.6-luna |
| after-final-2 | current_pack | multi-source-labeled-roots | PASS | 9/9 | — | 48 | 19419 | — | gpt-5.6-luna |

## Notes

The pre-change control passed the baseline scenario; two independent uncached post-change runs against the final implementation passed all 9 checks. The deterministic checker regression suite is the before/after evidence for the fix: the base checkers reject the pinned labeled-root dataflow, while the final checkers pass it and reject the unpinned-path escape cases. Checker regression coverage: [../../tests/test_labeled_root_checkers.py](../../tests/test_labeled_root_checkers.py).

## Evidence

Compact report: [`../records/multi-source-labeled-roots-regression-fix.json`](../records/multi-source-labeled-roots-regression-fix.json)
