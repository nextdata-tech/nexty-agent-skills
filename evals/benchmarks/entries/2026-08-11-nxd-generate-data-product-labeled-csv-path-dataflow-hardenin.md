---
id: "2026-08-11-nxd-generate-data-product-labeled-csv-path-dataflow-hardenin"
date: "2026-08-11"
label: "nxd-generate-data-product: labeled CSV path dataflow hardening"
plugin_version: "0.36.8"
status: "MIXED"
scenarios:
  - "multi-source-labeled-roots"
record: "../records/2026-08-11-nxd-generate-data-product-labeled-csv-path-dataflow-hardenin.json"
---
# Benchmark — nxd-generate-data-product: labeled CSV path dataflow hardening

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before | no_skills | multi-source-labeled-roots | FAIL | 8/9 | — | 35 | 12469 | — | gpt-5.6-luna |
| measured | current_pack | multi-source-labeled-roots | PASS | 9/9 | — | 39 | 16810 | — | gpt-5.6-luna |

## Notes

Final uncached Codex arms after hardening the labeled-root checker. The no-skills baseline scored 8/9 because its transform did not prove path-file dataflow into filesystem readers; current_pack scored 9/9 and the deterministic checker passed.

## Evidence

Compact report: [`../records/2026-08-11-nxd-generate-data-product-labeled-csv-path-dataflow-hardenin.json`](../records/2026-08-11-nxd-generate-data-product-labeled-csv-path-dataflow-hardenin.json)
