# Terminal authenticated DLT API ingestion

## Task for the agent

Read `BRIEF.md` and use only the connected `mcp__nxd-desktop__*` tools for the
data-product lifecycle. The runner provides `ENDPOINT_URL` for a local REST
fixture; treat it as the service described in the brief.

Build a small local data product that ingests the paginated `/v1/orders`
resource through the documented DLT REST connector. Put the endpoint topology,
auth scheme, bearer, and required client header in the declared api-source
profile attributes. The transform must read those flat attributes at runtime;
do not put the endpoint or credential in source, and do not use a hand-written
requests/urllib/httpx loop. Keep the source response envelope out of the
landed columns and preserve all three pages.

Materialize, publish, inspect the authoritative run, and run one governed
query over the landed rows. Then create independent negative cases under
`.eval-cases/` and run the same public MCP build/check path for each:

* `unauthorized-401`: omit or alter the bearer;
* `forbidden-403`: omit or alter the required client header;
* `unknown-endpoint-404`: use an endpoint path not declared by the profile;
* `malformed-profile`: make the declared api-source profile malformed;
* `omitted-profile`: remove the declared api-source profile input;
* `retired-companion`: add the retired `api-source-endpoints` file instead of
  declaring endpoints in the profile and prove it is rejected;
* `hard-coded-endpoint`: replace the transform's profile lookup with a literal
  topology and prove the closure is rejected.

For each negative case record the structured phase/code and do not call a
failed build successful. Keep the credential out of narration, generated
source, trace payloads, diagnostics, and export material. Stop the workflow
and clean up through the public supervisor tools.

## Success checks

The shipped contract declares endpoint attributes in `infra-profile.yaml`; the
old standalone `api-source-endpoints` file is intentionally not a supported
substitute. The withheld checker verifies the runner-authored MCP trace, the
DLT/profile architecture, the positive pagination contract, the six distinct
negative case records, and credential redaction. A static or hand-written HTTP
loop is not an acceptable substitute for DLT ingestion.
