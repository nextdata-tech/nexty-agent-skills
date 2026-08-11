---
id: "2026-08-11-nxd-generate-data-product-labeled-csv-roots-carried-via-comp"
date: "2026-08-11"
label: "nxd-generate-data-product: labeled CSV roots carried via companion-files"
plugin_version: "0.36.8"
status: "MIXED"
scenarios:
  - "multi-source-labeled-roots"
record: "../records/2026-08-11-nxd-generate-data-product-labeled-csv-roots-carried-via-comp.json"
---
# Benchmark — nxd-generate-data-product: labeled CSV roots carried via companion-files

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before | no_skills | multi-source-labeled-roots | FAIL | 8/9 | — | 29 | 9848 | — | gpt-5.6-luna |
| measured | current_pack | multi-source-labeled-roots | PASS | 9/9 | — | 15 | 9335 | — | gpt-5.6-luna |

## Notes

Uncached Codex no_skills origin/main baseline failed 8/9 because the trace did not prove reading all source shapes before authoring; its structural checker passed. The final current_pack arm passed 9/9 with the same finalized checker, and live supervisor pinning is registered separately as an opt-in desktop scenario.

## Evidence

Compact report: [`../records/2026-08-11-nxd-generate-data-product-labeled-csv-roots-carried-via-comp.json`](../records/2026-08-11-nxd-generate-data-product-labeled-csv-roots-carried-via-comp.json)
