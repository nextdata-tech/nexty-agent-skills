---
id: "2026-08-11-nxd-generate-data-product-labeled-csv-roots-carried-via-comp"
date: "2026-08-11"
label: "nxd-generate-data-product: labeled CSV roots carried via companion-files"
plugin_version: "0.36.8"
status: "PASS"
scenarios:
  - "multi-source-labeled-roots"
record: "../records/2026-08-11-nxd-generate-data-product-labeled-csv-roots-carried-via-comp.json"
---
# Benchmark — nxd-generate-data-product: labeled CSV roots carried via companion-files

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| measured | current_pack | multi-source-labeled-roots | PASS | 8/8 | — | 13 | 7024 | — | gpt-5.6-luna |

## Notes

Single uncached Codex observation: current_pack/multi-source-labeled-roots passed all 8 checks, including the authoritative directory-copy pin simulation and deliberate omission of the empty archive root. The first trial exposed an eval prompt/location mismatch because the agent followed the protected data_product convention; the scenario was corrected to require the closure at workspace root before this measured run. Agent and judge were Codex backends (gpt-5.6-luna and gpt-5.6-terra).

## Evidence

Compact report: [`../records/2026-08-11-nxd-generate-data-product-labeled-csv-roots-carried-via-comp.json`](../records/2026-08-11-nxd-generate-data-product-labeled-csv-roots-carried-via-comp.json)
