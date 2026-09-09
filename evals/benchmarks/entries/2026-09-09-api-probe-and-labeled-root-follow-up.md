---
id: "2026-09-09-api-probe-and-labeled-root-follow-up"
date: "2026-09-09"
label: "nxd-generate-data-product: authenticated probe and labeled-root checker follow-up"
plugin_version: "0.46.0"
status: "MIXED"
scenarios:
  - "authenticated-api-source-build"
  - "multi-source-labeled-roots"
record: "../records/2026-09-09-api-probe-and-labeled-root-follow-up.json"
---
# Benchmark — nxd-generate-data-product: authenticated probe and labeled-root checker follow-up

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before | current_pack | authenticated-api-source-build | FAIL | 15/16 | — | 16 | 11432 | — | gpt-5.6-luna |
| before | current_pack | multi-source-labeled-roots | PASS | 9/9 | — | 16 | 9123 | — | gpt-5.6-luna |
| after | current_pack | authenticated-api-source-build | PASS | 16/16 | — | 24 | 16849 | — | gpt-5.6-luna |
| after | current_pack | multi-source-labeled-roots | PASS | 9/9 | — | 34 | 13225 | — | gpt-5.6-luna |

## Notes

Follow-up to PR #248 after the original B-series benchmark: authenticated-api-source-build moves from 15/16 FAIL on the missing executed connectivity probe to 16/16 PASS, while multi-source-labeled-roots remains 9/9 PASS after the checker learns the safe literal dictionary-comprehension spelling. Both after cells have passing deterministic checks; the labeled-root checker change is additionally pinned by fail-closed positive and negative tests.

## Evidence

Compact report: [`../records/2026-09-09-api-probe-and-labeled-root-follow-up.json`](../records/2026-09-09-api-probe-and-labeled-root-follow-up.json)
