---
name: nxd-dp-static-artifact
description: Render one published NXD data-product release as a self-contained, offline HTML artifact. Use when the user asks to show, document, inspect, share, or create a static page for a published local data product or release. Read only the verified release catalog resources; never start a product, mint credentials, query rows, or substitute a partial catalog response.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
metadata:
  author: nextdata
  version: 0.25.0
---

# nxd-dp-static-artifact

Create exactly one release-scoped, self-contained offline HTML file. The file
describes what that release declares; it is not a catalog, a live dashboard, a
query surface, or a conversation widget. It may be previewed, but the
preview is the same completed file written to disk.

## Read and validate before rendering

Use only `nxd://` resources as payload input. Never call an nxd lifecycle,
catalog-action, or query tool to gather artifact content; local file operations
may only construct, validate, and atomically land the HTML output. In
particular, never use `list_data_products`, `describe_models`, `info`, a source
definition, a live endpoint, or a query as a fallback. A failed read is an
artifact failure, not permission to make a partial page.

1. Read the workflow's `current` resource, then read `verified.json` and
   `outputs` at its exact canonical `publish_seq`. Encode the workflow URI
   segment and require canonical decimal sequence text. Require
   `current.release_uri` to equal the canonical encoded `verified.json` URI.
   If the user requested another sequence, state that the requested release was
   superseded, name both sequences, and continue with the current bundle instead
   of returning an error or pretending the historical release was served.
2. Require `schema: nxd-desktop-verified-v1` and
   `trust: artifact_verified` on both `verified.json` and `outputs`; require
   `verified.release.workflow` / `verified.release.publish_seq` and
   `outputs.workflow` / `outputs.publish_seq` to equal `current`.
3. Require `current.definition_id` and `current.artifact_id` to equal
   `verified.release.definition_id` and `verified.release.artifact_id`.
   Require at least `workflow`, `publish_seq`, `run_id`, `definition_id`,
   `artifact_id`, `compiler_id`, and `published_at_unix_ms`. Do not accept or
   emit a `release_id`.
4. Use `data_model.models[].attributes` as the complete ordered display schema,
   then overlay roles from the same model/field in
   `models.models[].fields[].roles`. Validate every local role target and every
   local join endpoint. For a cross-product join with a non-empty
   `to_data_product`, validate the declared target identifiers without
   requiring that remote model in the local `data_model`.
5. Validate every output-level `model_names` / `models[].name` entry, then every
   `ports[].model_names` entry and every `ports[].models[].name` against the
   local display schema. Treat roles as a set
   and require every ordered model and attribute to be usable, including
   unannotated fields and complex `data_type` values.
6. On a superseded-release response, report the requested/current redirect and
   restart the whole bundle from `current`.
   Retry this bounded bundle at most twice. On a missing field, malformed value,
   unsupported schema, mismatch, orphan, read error, or third supersession,
   fail the whole artifact. Do not announce a partial artifact.

Keep artifact status separate from runtime health. A static-artifact failure
does not invalidate a healthy endpoint; a later governed query may still run.

## Render the complete semantic contract

Render this fixed semantic-first order. Do not add catalog, query, results, or
raw-payload screens.

1. **Identity** — name, description, version, and domain.
2. **Model overview** — each model's name, description, and grain/role summary.
3. **Complete schema** — every ordered `data_model` model and attribute;
   show the exact scalar or safely serialized complex type, description where
   present, semantic tags and constraints where present, and every overlaid
   role/PII marker. An unannotated field remains a field.
4. **Joins** — every declared endpoint and cardinality after validating both
   endpoints.
5. **Output exposure and ports** — render output-level `model_names` / `models`
   as their own declaration, then preserve each port and read its own
   `model_names` / `models`. Never replace either surface with a union. Render
   each port's service name and `promises`, including explicit `null` and `[]`
   states.
6. **Evidence** — only published artifact evidence. Show `compiler_id` only as
   evidence when non-zero; an all-zero ID is not meaningful provenance.
7. **Release provenance** — a closed-by-default `details` after evidence, with
   only `workflow`, `publish_seq`, `trust`, `definition_id`, `artifact_id`,
   `run_id`, and `published_at_unix_ms`.
8. **Diagnostics** — a closed-by-default `details` after provenance, limited to
   resource URIs, schema, and validation state. Never expose raw payloads.

Use the fixed glosses for values that are present as null or empty collections:
`null · the manifest didn’t say` and `[] · none declared`.
Render an optional field only when its key is present; an absent key produces
no label, slot, dash, or placeholder. Never render live-only `external_url`,
`environment`, `full_name`, `glossary`, or per-port `infra_profile_name`, and
never render the semantic registry's intentionally empty `data_product` or
`table`.

## File and safety contract

Build a sibling temporary file, validate it, then atomically rename it to
`<workflow>-release-<publish_seq>.html` in the selected safe directory. Escape
all payload-derived text and attribute values. If embedding JSON, escape
`</script>`, U+2028, and U+2029. Use a restrictive local CSP, system-font
fallbacks, and no remote scripts, fonts, requests, or live tool calls. On
failure remove/leave only the temp file per the host's safe cleanup semantics;
never replace an existing release artifact with partial output.

After a same-workflow rebuild, discard cached resource URIs and the prior
current-file assumption. The old file is historical; render the new sequence
before describing or querying the rebuilt product.

## Reference artifacts

Use [reference/contract.md](reference/contract.md) for the exact validation
matrix and [reference/pitfalls.md](reference/pitfalls.md) for safety failures.
`assets/artifact-example.html` is the complete offline example; `assets/kit.html`
is the component reference. Do not use either as a source of live data.

## Verify before handoff

- [ ] One completed offline HTML file, no remote URL, no Query/Catalog/results UI
- [ ] All data-model fields, complex types, multi-role fields, joins, output-level models, ports and promises shown
- [ ] Evidence precedes closed Release provenance and closed Diagnostics
- [ ] Provenance contains only its allowlist; Diagnostics contains only allowed fields
- [ ] All resource and semantic validation passed as one exact release bundle
- [ ] Handoff separately states artifact status, path, and publish sequence
