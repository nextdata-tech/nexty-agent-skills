---
id: "2026-08-11-nxd-generate-data-product-labeled-csv-roots-final-review"
date: "2026-08-11"
label: "nxd-generate-data-product: labeled csv roots final review"
plugin_version: "0.36.8"
status: "PASS"
scenarios:
  - "multi-source-labeled-roots"
record: "../records/2026-08-11-nxd-generate-data-product-labeled-csv-roots-final-review.json"
---
# Benchmark — nxd-generate-data-product: labeled csv roots final review

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| current_pack | current_pack | multi-source-labeled-roots | PASS | 9/9 | — | 55 | 17353 | — | gpt-5.6-luna |
| no_skills | no_skills | multi-source-labeled-roots | PASS | 9/9 | — | 35 | 11530 | — | gpt-5.6-luna |

## Notes

Fresh uncached Codex runs after the review fixes: current_pack and no_skills both passed 9/9. The paired result validates the scenario but does not yet show skill-set differentiation.

## Evidence

Compact report: [`../records/2026-08-11-nxd-generate-data-product-labeled-csv-roots-final-review.json`](../records/2026-08-11-nxd-generate-data-product-labeled-csv-roots-final-review.json)
