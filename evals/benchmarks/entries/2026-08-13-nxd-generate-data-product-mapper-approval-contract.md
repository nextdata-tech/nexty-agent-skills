---
id: "2026-08-13-nxd-generate-data-product-mapper-approval-contract"
date: "2026-08-13"
label: "nxd-generate-data-product: mapper approval contract rerun"
plugin_version: "0.37.1"
status: "PASS"
scenarios:
  - "generate-runnable-dp-from-intent"
record: "../records/2026-08-13-nxd-generate-data-product-mapper-approval-contract.json"
---
# Benchmark — nxd-generate-data-product: mapper approval contract rerun

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-origin-main | current_pack | generate-runnable-dp-from-intent | PASS | 16/16 | — | 13 | 7117 | — | gpt-5.6-luna |
| after-mapper-approval | current_pack | generate-runnable-dp-from-intent | PASS | 16/16 | — | 19 | 7926 | — | gpt-5.6-luna |

## Notes

Reran the runnable data-product generation scenario locally with the Codex agent/judge backend because the Claude CLI was not authenticated. Both arms used identical runner/model settings and passed all 16 checks. The live Desktop mapper-admission path is not exercised by this public scenario; its separate deterministic supervisor/skills contract tests passed 744 tests after the review fixes.

## Evidence

Compact report: [`../records/2026-08-13-nxd-generate-data-product-mapper-approval-contract.json`](../records/2026-08-13-nxd-generate-data-product-mapper-approval-contract.json)
