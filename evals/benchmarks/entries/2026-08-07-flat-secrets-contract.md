---
id: "2026-08-07-flat-secrets-contract"
date: "2026-08-07"
label: "nxd-generate-data-product: secrets is one flat map, not a per-service dict"
plugin_version: "0.36.6"
status: "MIXED"
scenarios:
  - "authenticated-api-source-build"
record: "../records/2026-08-07-flat-secrets-contract.json"
---
# Benchmark — nxd-generate-data-product: secrets is one flat map, not a per-service dict

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before | current_pack | authenticated-api-source-build | FAIL | 5/15 | — | 22 | 21857 | — | gpt-5.6-luna |
| after | current_pack | authenticated-api-source-build | PASS | 15/15 | — | 17 | 16616 | — | gpt-5.6-luna |

## Notes

Measured arm for the flat-secrets contract correction. Both arms are codex/gpt-5.6-luna agent + gpt-5.6-terra judge, run in CI, and graded by the SAME corrected harness: the before arm is b611c3e with src/ reverted to 0e73180 (evals/ byte-identical, verified empty diff), so only the skill docs differ. This matters because the same change retargeted both checks.json and the deterministic checker; grading the arms with different harnesses would compare graders rather than the change. Before: overall_pass False, 5/15 checks, deterministic_check failed. After: overall_pass True, 15/15, deterministic_check passed. The ten checks that flip are the ones downstream of reading the connector config - an agent following the old docs emits secrets['api_source']['base_url'] and raises KeyError at transform time, after the credential has resolved, so the closure never reaches a gradeable state.

## Evidence

Compact report: [`../records/2026-08-07-flat-secrets-contract.json`](../records/2026-08-07-flat-secrets-contract.json)
