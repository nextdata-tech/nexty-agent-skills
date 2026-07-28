# The data contract

What the payloads guarantee, and what a rendered surface may claim on their behalf.

## Contents

- [Absence has three different meanings](#absence-has-three-different-meanings)
- [The value states](#the-value-states)
- [Where each block sits](#where-each-block-sits)
- [The role vocabulary is closed](#the-role-vocabulary-is-closed)
- [The union trap](#the-union-trap)
- [Identifiers](#identifiers)
- [Addressing and failure](#addressing-and-failure)
- [Query results](#query-results)
- [What must never be rendered](#what-must-never-be-rendered)

## Absence has three different meanings

**This is the rule most likely to be got wrong, because the obvious version of it
is false.** There is no single "absent means X" for this surface. A missing key
means one of three different things depending on which block it is missing from,
and rendering them identically states something untrue.

| Where | Absence means | Render |
|---|---|---|
| `info.identity`, `outputs` — live-only fields | **This surface cannot know.** The pinned shape does not declare the field at all | Nothing. Diagnostic mode may reveal it |
| `data_model[].attributes[]` — `description`, `semantic-tags`, constraints | **The attribute declared none.** `skip_serializing_if` omits the empty case | Nothing, and nothing is missing — a plain typed column is legitimately `{name, data_type}` |
| `list_data_products` — `definition_id`, `run_id`, `publish_seq`, `published_at_unix_ms` | **The Release could not be read.** Always paired with `artifact_status: "release_unreadable"` | Degraded row, surfacing the `error` field |

The third is the dangerous one. Those keys are omitted *precisely so an agent
cannot mistake a zero or an empty string for a real value*. A UI that renders
them as blank slots re-introduces the ambiguity the wire shape removed. Branch on
`artifact_status` first; do not infer damage from a missing key.

Do not write a generic "if key absent, skip" helper and apply it everywhere. The
three cases need three different treatments.

## The value states

Within a block, a *present* key still carries state:

| State | Payload | Means | Render |
|---|---|---|---|
| Present | `"version": "0.0.1"` | A fact | Normal value, `--text-primary` |
| Null | `"description": null` | The manifest did not say | Visible slot, italic, `--text-muted` |
| Empty | `"model_names": []` | None declared — an answer, not a gap | Visible slot with `[]` and a gloss |

`null` and `[]` must be distinguishable from each other and from a present value.
An empty collection always serializes; treating it as missing data loses the
affirmative "none".

The glosses are fixed strings. Copy them byte-for-byte, including the typographic
apostrophe:

- `null · the manifest didn’t say`
- `[] · none declared`

`assets/kit.html` uses U+2019 (`’`) at every site. If a check string-matches a
gloss, an ASCII `'` fails it.

## Where each block sits

| Resource | Carries |
|---|---|
| `current` | `workflow`, `publish_seq`, `definition_id`, `artifact_id`, pre-built `release_uri` |
| `info` | `identity`: `name`, `domain`, `description`, `version` |
| `models` | `models`: the semantic registry, verbatim from the canonical compiler |
| `outputs` | `outputs`: `model_names`, `models`, `ports` |
| `verified.json` | `release`, `evidence`, `identity`, `services`, `models`, `data_model` |

`verified.json` carries two model blocks that are **not** interchangeable:

- **`models`** — the semantic registry the query engine consumes. Lists only
  fields carrying a semantic role. No `semantic-tags`, no constraints.
- **`data_model`** — display-only. Every model and **every** attribute, including
  ones with no semantic role and therefore invisible to `models`. Carries
  per-attribute `data_type`, description, `semantic-tags`, constraints.

Use `data_model` to show the whole product. Use `models` for anything that feeds
a query. Nothing in `data_model` reaches the query compiler.

`data_type` renders exactly as the manifest carries it: a bare string for a
scalar (`"string"`, `"number"`), an object for a complex type
(`{"timestamp": {"unit": "ms"}}`, list, struct, map, decimal). A renderer that
assumes a string breaks on the complex case.

## The role vocabulary is closed

Four kinds: `dimension`, `metric`, `join`, `primary_key`.

**Do not write an unknown-kind fallback.** The registry deserializes roles
through a tagged enum; an unrecognised kind fails the read, and the resource
returns an error rather than a partial document. No payload containing an unknown
kind can reach a renderer.

A degradation path here is unreachable code that also cannot be tested — a
fixture exercising it asserts a payload the server refuses to emit. If the
vocabulary ever opens, the read stops failing first, and that is the signal to
add rendering.

What *does* need handling is the read failing: a malformed annotation surfaces as
an error on the whole resource. Render that, not a neutral badge.

`roles` is a **set**. One column can be primary key *and* the basis of a metric.
Draw every role it carries.

## The union trap

Top-level `outputs.model_names` lists models declared at the **output level
only**. It is not a union across ports.

A product declaring its models under each port reports an **empty** top-level
list and populated per-port lists. Reading only the top level and concluding "no
models" is wrong. Walk `ports[].model_names`.

The projection refuses to union on your behalf because a live deployment reports
the same shape for the same manifest; unioning would make an artifact read
disagree with a live read.

## Identifiers

`list_data_products` returns **no human name**. Its `ProductEntry` carries
`workflow`, `artifact_id`, `models`, `artifact_status` and the read-dependent
keys above. The human name lives in `info.identity.name` — a resource read.

So a catalog rendered from the tool alone can only show the `workflow`. To show
human names, read `info` per product. Do not invent a display name by
prettifying the workflow.

`workflow` is the identifier passed to tools. Where both are shown, show the name
and pass the workflow — they are different strings.

Treat `published_at_unix_ms`, `publish_seq` and `row_count` as numbers. Format
them; do not concatenate.

Hashes (`definition_id`, `artifact_id`, `run_id`, `compiler_id`) are long:
truncate on screen, keep the full value copyable. `compiler_id` can be all zeros
in fixtures — not a meaningful hash, do not present it as provenance.

## Addressing and failure

Build every URI by encoding, never by concatenation:

```js
const uri = `nxd://data-products/${encodeURIComponent(workflow)}/releases/${seq}/models`;
```

A workflow containing `/` becomes `%2F` and stays one segment. `{seq}` is
canonical decimal — `007` is malformed, not `7`.

Only the current release is readable. Three failure kinds:

- **`resource_not_found` with a newer `current_publish_seq`** — superseded. The
  payload carries `current_uri`. This is a **redirect**: re-fetch and say so.
  Never a dead end.
- **`artifact_unavailable`** — data garbage-collected or failed integrity checks.
  Marked **not retryable**. Rebuild; re-reading will not help.
- **`workflow_not_found`** — nothing published under that workflow. Carries
  `available_workflows`.

## Query results

`run_semantic_query` caps at **200 rows** regardless of the requested limit, and
sets `truncated` when the cap is hit. Surfacing that is mandatory — a silent
partial set is the worst failure this surface can produce, because the user draws
conclusions from incomplete data believing it complete.

Queryable names come from the semantic registry. Physical table names in evidence
(`main.customers`) are **not** queryable identifiers; offering them as such
produces a failing query.

## What must never be rendered

- **Connection config, driver types, credentials.** Not on this surface at all.
  `infra_service_name` is a service *name* only.
- **The `bearer_token`.** Never displayed, never persisted, never in a URL.
- **A model's `data_product` or `table` from the `models` registry.** The desktop
  adapter passes empty strings for both — it asserts nothing about physical
  placement. Empty here is an adapter decision, not a wire-level statement, so
  do not read meaning into it either.
- **Anything obtained by calling a tool during render.** See
  [behaviour.md](behaviour.md).
