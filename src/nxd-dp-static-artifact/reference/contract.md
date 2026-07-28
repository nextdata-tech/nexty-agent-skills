# Release bundle contract

## Contents

- [Required reads](#required-reads)
- [Read transports](#read-transports)
- [Cross-document equality](#cross-document-equality)
- [Semantic validation](#semantic-validation)
- [Safe output](#safe-output)
- [Failure boundary](#failure-boundary)

## Required reads

Read only `current`, then the matching release-scoped `verified.json` and
`outputs`. Address the workflow as one encoded URI segment and the sequence as
canonical decimal. Require `current.release_uri` to equal that exact canonical
encoded `verified.json` URI. `current` selects the only valid release bundle.

Both release documents must carry `schema: nxd-desktop-verified-v1` and
`trust: artifact_verified`. Unsupported schema or trust is a failed artifact,
not an invitation to guess a compatible shape.

If the user names a non-current sequence, or a release read returns
`requested_publish_seq`, `current_publish_seq`, and `current_uri`, treat it as
a redirect rather than a dead end: tell the user the requested sequence was
superseded, name the current sequence, discard any partial bundle, and render
the current release. Never claim that the historical payload itself was read.

## Read transports

The bundle is defined by the documents, not by how they were fetched. Two
transports deliver them:

| Transport | Use when | List | Read |
|---|---|---|---|
| Native MCP resources | the client exposes resource operations | `resources/list` | `resources/read` |
| `nxd-desktop` bridge tools | it does not | `list_data_product_resources` | `read_data_product_resource` |

Both are read-only, take no lock, boot no runtime, and return no credentials.
The server implements them over one reader, so the uri grammar, document bytes,
mime type, and every error code and payload are identical — including the
supersession redirect carrying `requested_publish_seq`, `current_publish_seq`,
and `current_uri`. Validate an assembled bundle exactly the same way regardless
of transport; nothing in this contract relaxes for the bridge.

Two rules constrain the choice:

- **Decide before the first read, and keep it for the whole bundle.** Documents
  fetched through different transports must not be combined, even though they
  would be byte-identical. Mixing forfeits the single-transport guarantee that
  makes a bundle auditable.
- **Only a missing client capability justifies the bridge.** That is a property
  of the client, established before reading. A resource read that returns an
  error has answered — re-asking through the bridge returns the same error from
  the same reader, so treating a domain failure as a transport failure buys
  nothing and risks reporting a release state that was never read.

## Cross-document equality

Require `current.workflow` / `current.publish_seq`,
`verified.release.workflow` / `verified.release.publish_seq`, and
`outputs.workflow` / `outputs.publish_seq` to agree. Require schema and trust
equality only between `verified.json` and `outputs`. Require
`current.definition_id` and `current.artifact_id` to equal the corresponding
`verified.release` values.

`verified.release` must contain at least `workflow`, `publish_seq`, `run_id`,
`definition_id`, `artifact_id`, `compiler_id`, and `published_at_unix_ms`; no
`release_id` exists in this contract. Reject a malformed or missing value. Do
not reject supported additional fields or compare fields that a document does
not contractually carry.

## Semantic validation

`data_model.models` is the complete display model. Preserve its order and
include each attribute, even when it has no role. Serialize complex
`data_type` values as safe JSON rather than coercing them to a string. Render
optional attribute descriptions, `semantic_tags`, and `constraints` only when
their keys are present.

Overlay `models.models[].fields[].roles` onto matching
`data_model.models[].attributes`; never render the semantic registry's
intentionally empty `data_product` or `table` fields. A role list is a set:
preserve all roles on a field. Resolve local role targets and both endpoints of
local joins against `data_model`. A join with a non-empty `to_data_product` is
cross-product: require its declared remote model/column identifiers, but do not
require the remote model to appear locally. Resolve output-level references
from `model_names` and `models[].name`, then resolve each per-port reference
independently from `ports[].model_names` and `ports[].models[].name`. Never
replace those surfaces with a union. A missing local target, endpoint, or output
model makes the entire artifact invalid.

## Safe output

Treat every payload value as hostile. Escape text and attributes. Escape JSON
embedded in a script element by replacing `</script>` with `<\\/script>` and
U+2028/U+2029 with their `\\u` forms. Emit no remote resource, no live fetch,
and no generated raw payload inspector. Use system fonts plus an offline CSP.

Write a sibling temporary file and atomically rename only after all validation
and final-file checks pass. The destination name is
`<workflow>-release-<publish_seq>.html` after safe filename encoding. A prior
release file is historical after a rebuild; never relabel it as current.

## Failure boundary

On any read failure, mismatch, malformed document, orphan, unsupported schema,
or failed atomic write, report `artifact: failed` with the reason. Preserve the
separate endpoint state. A healthy endpoint may still be described and queried;
the artifact must not be represented as having succeeded.

Switching transports is never part of this recovery. A failed read is a fact
about the release; the other transport reads the same bytes through the same
reader and will fail identically.

For a superseded read, discard all collected documents and restart from
`current`; attempt the full bundle no more than twice. Never mix documents from
two release sequences.
