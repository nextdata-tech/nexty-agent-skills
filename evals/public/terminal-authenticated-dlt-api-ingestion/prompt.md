# Terminal authenticated DLT API ingestion

## Task for the agent

Read `BRIEF.md` and use only the connected `mcp__nxd-desktop__*` tools for the
data-product lifecycle. The runner provides `ENDPOINT_URL` for a local REST
fixture and `NXD_EVAL_SOURCE_TOKEN` for the sensitive runtime profile; treat
both as runner-provided inputs, never as values to repeat.

Build a small local data product that ingests the paginated `/v1/orders`
resource through the DLT REST connector. Put the base URL, auth scheme, bearer,
and required client header in the `api-source` profile attributes. Declare
`api-source-endpoints` in the root `companion-files` manifest and put the
`orders=/v1/orders` topology there. The transform must read the profile and
companion at runtime from the materialized closure root; do not put the
endpoint or credential in source, and do not use a hand-written
requests/urllib/httpx loop. Keep the source response envelope out of the
landed columns and preserve all three pages.

Use the current workflow-v2 MCP lifecycle: capability-gate, prepare, advance
through capture/review/admission/publication, inspect both the durable workflow
and the authoritative admitted run (`inspect_run`), list/resume the published
product, describe its models, run one governed query using the returned
endpoint/token and a `status = paid` dimension filter, and export it to a path
below the workspace so its archive can be checked.
Then create independent negative cases under `.eval-cases/` and run the same
public MCP check/admission path for each:

* `unauthorized-401`: omit or alter the bearer;
* `forbidden-403`: omit or alter the required client header;
* `unknown-endpoint-404`: use an endpoint path not served by the fixture;
* `malformed-companion`: keep the manifest but make the endpoint map malformed;
* `omitted-companion`: declare the companion but omit the file;
* `hard-coded-endpoint`: replace the transform's companion lookup with a
  literal topology and prove the closure is rejected.

For each negative case record the structured phase/code returned by the public
MCP path and do not call a failed check or build successful. Keep the credential
out of narration, generated source, companion topology, trace payloads,
diagnostics, and export material. Do not invent a stop/cancel MCP method: after
the final public call, leave process and temporary-state cleanup to the runner.

## Success checks

The shipped contract declares `api-source-endpoints` as a materialized
companion, while credentials remain in the sensitive profile. The withheld
checker verifies the runner-authored JSON-RPC trace, the DLT/companion
architecture, separate unfiltered pagination and filtered-query observations,
materialization and publication evidence, six trace-linked negative cases,
export redaction, and cleanup. A static or hand-written HTTP loop is not an
acceptable substitute for DLT ingestion.
