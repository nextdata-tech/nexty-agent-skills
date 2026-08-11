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

Adds the header_<name> profile-attribute convention and the client['headers'] assembly to reference/api-source.md, plus a User-Agent-gated stub and four deterministic header facts. Both arms face the same header-gated fixture and both sit on top of #177, so the only variable is the recipe. FACT-LEVEL before -> after: header:declared-in-profile FAIL -> PASS; header:non-secret-marked-public FAIL -> PASS; ingestion:no-hardcoded-url-or-path FAIL -> PASS; closure:materializes FAIL (HTTP 403) -> PASS; every landed:* unverifiable -> PASS. The before arm hardcoded the User-Agent into transform/main.py and still 403ed under re-materialization, so its 9/16 counts checks the runner could not evaluate, not ones it evaluated and passed; the after arm materializes and every landed-data trap is confirmed against real rows. WHAT THIS DID NOT FIX: ingestion:rest-api-resources-used FAILS on BOTH arms -- the agent hand-rolls requests instead of dlt's REST connector, which is the defect NEX-873 was filed about. This change makes the header expressible on the dlt path without making the hand-rolled path unattractive. The after arm shows the recipe partly landing anyway: the agent wrote header_user_agent into the profile, marked it public, and read it back from the flat secrets map -- then passed it to a requests loop. The convention was learned; the architecture was not held. The binding constraint is the acceptance check, not the recipe: uses_rest_api_resources is presence-only and cannot reject a closure that imports dlt AND hand-rolls beside it. Tightening it is the next commit, deliberately NOT done mid-benchmark because moving the checker between arms would invalidate this comparison. Carrying tests: evals/tests/test_api_source_header_contract.py.

## Evidence

Compact report: [`../records/2026-08-11-api-source-custom-client-headers.json`](../records/2026-08-11-api-source-custom-client-headers.json)
