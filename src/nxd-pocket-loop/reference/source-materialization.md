# Materializing a source faithfully

How each kind of in-scope source is landed at Step 1, before inference. These
rules govern **source materialization only** and they are absolute — everything
downstream depends on the landed rows being a byte-exact record of what the user
supplied.

## Contents

- [Fidelity here; derivation downstream](#fidelity-here-derivation-downstream)
- [Attached or workspace file](#attached-or-workspace-file)
- [Pasted table](#pasted-table)
- [Database connection](#database-connection)
- [REST API](#rest-api)
- [Host path handoff](#host-path-handoff)

## Fidelity here; derivation downstream

The CSVs you land are a byte-exact record of what the user supplied, so any
later number traces back to it. Cleaning, dedup, amortization, currency
normalization, reclassification and regrain are legitimate — often necessary —
but exist **only as derived models computed downstream of the pristine source**,
never as an edit to the source export. Preserve the row on the way in, then
derive the corrected model beside it; `nxd-generate-dp` owns how.

Materialization is also **gated**: if the request supplied a procedure with a
result-changing gap, copying a source into a closure waits for the user's reply
to the `dp-spec.md` read-back. Reading a source is always allowed.

With 2+ sources, repeat the matching section once per source and tag every
artifact with that source's label.

## Attached or workspace file

Make an exact byte-for-byte copy into the generated connector export. Do not
rewrite delimiter, encoding, headers, or rows.

## Pasted table

Materialize every supplied header and value faithfully in a separate CSV export.
Do not add columns, coerce values, deduplicate rows, or invent an identifier;
treat prose before or after the table as narrative, not a data row.

A header followed by consistently shaped rows is sufficient evidence to proceed
— don't claim a value was spliced, truncated, or missing merely because the chat
renderer visually wraps the prompt. Ask only on a real structural ambiguity: a
row with a different field count, or an unparseable value.

## Database connection

Record host/port/database/schema, the table(s)/view(s) the user explicitly
named, and the live credentials supplied now. Treat access as **read-only** and
never invent a table name.

## REST API

Record the base URL, auth scheme, the endpoint(s)/resource(s) in scope, a sample
response shape if available, any known pagination, and the live token/key if
auth is required. Treat access as **read-only** and never fabricate an endpoint.

## Where credentials land

A database or API credential lands in exactly one place: the generated
`infra-profile.yaml` connector service's `attributes`. Never in chat, never in
`dp-spec.md` (which names key names only), never in a subagent's prompt or
return. Per-type shape is in `nxd-generate-dp`'s `reference/database-source.md`
and `reference/api-source.md`; labeled instances in its
`reference/multi-source.md`.

## Host path handoff

Pass `build_data_product` only the host-visible, absolute output path explicitly
returned or exposed by the file-writing tool. Never derive a definition path
from an opaque attachment ID, a tool-internal ID, or a Linux workspace path. If
no such path is available, stop and explain that the local build cannot reach
the materialized definition yet.
