---
id: "2026-08-11-api-source-custom-client-headers"
date: "2026-08-11"
label: "nxd-generate-data-product: custom HTTP client headers on the dlt REST path (NEX-873)"
plugin_version: "0.37.0"
status: "FAIL"
scenarios:
  - "authenticated-api-source-build"
record: "../records/2026-08-11-api-source-custom-client-headers.json"
---
# Benchmark — nxd-generate-data-product: custom HTTP client headers on the dlt REST path (NEX-873)

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.36.7 | current_pack | authenticated-api-source-build | FAIL | 9/16 | 129 | 126 | 97745 | 9.32 | sonnet |
| after-v0.37.0 | current_pack | authenticated-api-source-build | FAIL | 14/16 | 88 | 85 | 82069 | 6.70 | sonnet |

## Notes

Adds the header_<name> profile-attribute convention and the client['headers'] assembly to reference/api-source.md, plus a User-Agent-gated stub and four deterministic header facts. Both arms face the same header-gated fixture and both sit on top of #177, so the recipe is the only variable between them. BOTH ARMS RAN THE CLAUDE BACKEND (sonnet agent, opus judge). That matters more than it looked when these were recorded: the SAME scenario, same commit, scores 16/16 PASS on the CODEX backend the automatic PR gate uses (gpt-5.6-luna / gpt-5.6-terra, run 31538883570, 22 tool calls / 18240 output tokens). So the numbers below measure the recipe's effect on a sonnet agent, not a ceiling on the skill, and the ingestion:rest-api-resources-used failure discussed below is backend-specific rather than universal. FACT-LEVEL before -> after (claude): header:declared-in-profile FAIL -> PASS; header:non-secret-marked-public FAIL -> PASS; ingestion:no-hardcoded-url-or-path FAIL -> PASS; closure:materializes FAIL (HTTP 403) -> PASS; every landed:* unverifiable -> PASS. The before arm hardcoded the User-Agent into transform/main.py and still 403ed under re-materialization, so its 9/16 counts checks the runner could not evaluate, not ones it evaluated and passed; the after arm materializes and every landed-data trap is confirmed against real rows. WHAT THIS DID NOT FIX ON THE CLAUDE BACKEND: ingestion:rest-api-resources-used FAILS on both claude arms -- the agent hand-rolls requests instead of dlt's REST connector. The after arm shows the recipe partly landing anyway: it wrote header_user_agent into the profile, marked it public, and read it back from the flat secrets map -- then passed it to a requests loop. The convention was learned; the architecture was not held. That motivated tightening uses_rest_api_resources from presence-only to a hybrid-rejecting gate (a closure importing rest_api_resources while requests fetches the rows beside it no longer passes), deliberately NOT done mid-benchmark because moving the checker between arms would invalidate this comparison. The codex run above passes that tightened gate, so it is satisfiable, not merely stricter. Carrying tests: evals/tests/test_api_source_header_contract.py, evals/tests/test_api_source_connector_gate.py.

## Evidence

Compact report: [`../records/2026-08-11-api-source-custom-client-headers.json`](../records/2026-08-11-api-source-custom-client-headers.json)
