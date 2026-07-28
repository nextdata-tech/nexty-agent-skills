# Render the published release and answer a question

The eval runner provides only release catalog documents under `fixtures/`.
Create a self-contained offline HTML artifact for workflow `customer/health`,
whose stakeholder initially asked for release 1, then explain what model can
answer monthly revenue. `requested-release-1.json` says that release was
superseded: state the redirect and render the current release rather than
returning an error. Do not call a runtime, query data rows, use
`list_data_products` as a data source, or fetch anything from the network.

Read `current.json`, then the matching `verified.json` and `outputs.json` as
one release bundle. Treat `mismatch.json`, `missing-release.json`, and
`list-fallback.json` as failure/temptation fixtures, not alternate inputs.

`bridge-read-verified.json` and `bridge-read-release-1.json` show what the
read-only `read_data_product_resource` bridge returns for those same uris on a
client exposing no MCP resource operations: the identical sealed document, and
the identical supersession redirect. They are reference shapes, not a second
bundle — never combine bridge-read and resource-read documents in one bundle,
and never reach for the bridge to retry a read that already returned an error.
Show every declared schema field, including unannotated and complex fields,
all role markers, validated joins, each port and its promises. Place evidence
before closed Release provenance and closed Diagnostics. Escape all hostile
payload text. State the artifact path and publish sequence separately from any
later query answer.

## Success checks

The static page is all-or-nothing: schema/trust mismatch, missing release data,
or an orphan target produces no artifact. A list response never fills the gap.
