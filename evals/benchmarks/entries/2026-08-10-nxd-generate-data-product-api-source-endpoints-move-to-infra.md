---
id: "2026-08-10-nxd-generate-data-product-api-source-endpoints-move-to-infra"
date: "2026-08-10"
label: "nxd-generate-data-product: api-source endpoints move to infra-profile attributes"
plugin_version: "0.36.7"
status: "MIXED"
scenarios:
  - "authenticated-api-source-build"
record: "../records/2026-08-10-nxd-generate-data-product-api-source-endpoints-move-to-infra.json"
---
# Benchmark — nxd-generate-data-product: api-source endpoints move to infra-profile attributes

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| harness-gap | current_pack | authenticated-api-source-build | FAIL | 3/15 | — | 21 | 13958 | — | gpt-5.6-luna |
| measured | current_pack | authenticated-api-source-build | PASS | 15/15 | — | 31 | 14274 | — | gpt-5.6-luna |

## Notes

Single observation per arm, not a five-run measurement, and the two arms differ by an EVAL HARNESS fix (01b51da) rather than by any skill change: both ran this branch's skills. In the harness-gap arm the checker required the endpoint map to live in infra-profile.yaml but _MATERIALIZE_HARNESS still built the transform's secrets from base_url/auth_type/auth_token only, so a transform obeying the new contract had no legal source for the path and died with KeyError: 'endpoint_checks'. All three new contract checks - closure:endpoints-in-profile, closure:endpoints-public, closure:no-endpoints-companion - passed in that arm, so the FAIL is the harness withholding the attributes, not the skill. Two pre-fix runs were observed; the retained report for this arm is the 3/15 one, the other reached 5/15, and both died at the same KeyError. Threading the endpoint attributes through materialize_closure takes the scenario to 15/15 with deterministic exit 0. The cell is now entered in evals/baselines/public.json (3df0cd1) so a future regression to FAIL gates instead of passing silently. Both arms: codex backend, gpt-5.6-luna agent, gpt-5.6-terra judge, EVAL_CODEX_AGENT_SANDBOX=danger-full-access, which is what CI uses. The full 19-scenario suite and the worldbank-live run from the same session predate the harness fix and are not recorded here.

## Evidence

Compact report: [`../records/2026-08-10-nxd-generate-data-product-api-source-endpoints-move-to-infra.json`](../records/2026-08-10-nxd-generate-data-product-api-source-endpoints-move-to-infra.json)
