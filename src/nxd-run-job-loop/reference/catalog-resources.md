# Reading a built product's catalog resources

## Contents

- [Resources vs. tools](#resources-vs-tools)
- [The five resources](#the-five-resources)
- [Addressing: only the current release is readable](#addressing-only-the-current-release-is-readable)
- [What each document carries](#what-each-document-carries)
- [Pinned, not live — what is deliberately absent](#pinned-not-live--what-is-deliberately-absent)
- [Reading `outputs` without the union trap](#reading-outputs-without-the-union-trap)
- [Static artifact lifecycle](#static-artifact-lifecycle)
- [When a read fails](#when-a-read-fails)

## Resources vs. tools

The `nxd-desktop` server exposes two different surfaces, and they answer
different questions:

- **Tools** (`mcp__nxd-desktop__…`) are *actions*: check, build, resume, list,
  inspect, describe, query, export. Most take locks, boot runtimes, or mint
  bearers; `check_data_product` is the no-lock, no-publish admission check.
- **Resources** (`nxd://…`) are *read-only documents* projected from the pinned
  artifact bytes of a published release. Reading one takes no lock, boots
  nothing, and cannot disturb a running instance.

Reach for a resource when you want to know **what a published product
declares** — its identity, its model registry, its output ports. Reach for a
tool when you want to *do* something or when you need live runtime state.

`describe_models` remains the right call when you are about to build a query —
it is the query-facing view, and it requires a live `endpoint` and bearer
`token`. The `models` resource needs **neither**: it reads the pinned artifact
bytes, so it answers for a product that is published but not currently served.
Use it to show a user what shipped, or to read a product's shape before
deciding whether to resume it.

### When the client exposes no resource operations

Some clients connect to the server, receive `resources/list` fine, and still
never surface resource listing or reading to the agent. Two read-only tools
bridge exactly that gap:

| Tool | Equivalent to |
|---|---|
| `list_data_product_resources` | `resources/list` |
| `read_data_product_resource` (takes `uri`) | `resources/read` |

They are the one place a *tool* may supply pinned-document content. The server
implements them over the same reader as the resource methods, so the documents,
mime types, and error payloads are identical — they take no lock, boot no
runtime, and return no credentials. They are still the fallback, not the
default: prefer the resource operations whenever the client offers them, and
reach for the bridge only on the client's lack of that capability, never to
retry a read that failed.

## The five resources

All five are `application/json`, and all five are advertised by
`resources/list` for every workflow with a readable current pointer:

| URI | Document |
|---|---|
| `nxd://data-products/{wf}/current` | Release pointer: which release is current |
| `nxd://data-products/{wf}/releases/{seq}/verified.json` | Verified artifact catalog + evidence |
| `nxd://data-products/{wf}/releases/{seq}/info` | Manifest-declared identity |
| `nxd://data-products/{wf}/releases/{seq}/models` | Semantic model registry |
| `nxd://data-products/{wf}/releases/{seq}/outputs` | Declared output ports and models |

`{wf}` is the workflow name **URL-encoded** — a workflow named `team/data`
addresses as `nxd://data-products/team%2Fdata/current`. Don't hand-assemble a
URI from a raw name containing `/`, `%`, or spaces; take the URI from
`resources/list` instead.

## Addressing: only the current release is readable

`{seq}` is the release's `publish_seq`. The catalog serves **only the current
release**: a read for a superseded `{seq}` is rejected with
`resource_not_found`, not silently answered with newer bytes. The error payload
carries `requested_publish_seq`, `current_publish_seq`, and a `current_uri` to
retry against.

This means a `{seq}` you cached earlier can go stale after a rebuild. The
durable move is:

1. read `nxd://data-products/{wf}/current` to learn the current `publish_seq`, then
2. address the release-scoped resources with that value.

Or just re-read `resources/list`, which always advertises the current seq.

Rebuilding through `build_data_product` with the same `workflow` advances
`publish_seq`. After any rebuild, discard cached URIs.

## What each document carries

Every release-addressed document is stamped with the same provenance header:

```json
{
  "schema": "nxd-desktop-verified-v1",
  "trust": "artifact_verified",
  "workflow": "sales",
  "publish_seq": 1
}
```

`trust: "artifact_verified"` means the payload was projected from the pinned,
published artifact bytes — not from a live runtime and not from the source
definition directory. Cite it as what the product *declares*.

**`info`** adds an `identity` block: `name`, `domain`, `description`, `version`.
`description` is `null` when the manifest omits it.

**`models`** adds a `models` block: the semantic registry, compiled through the
same canonical grammar `describe_models` and `verified.json` use. Same models,
same roles, same joins.

**`outputs`** adds an `outputs` block: `model_names`, `models`, and `ports`,
where each port carries `name`, `infra_service_name`, its own `model_names` and
`models`, and `promises` (`null` when the port declares none).

`infra_service_name` is a **service name only** — never a driver type,
connection config, or credential.

## Pinned, not live — what is deliberately absent

These documents describe an artifact, not a deployment. Facts that only a
running data product can answer are **structurally absent** — the key is not
present at all, rather than present-and-null:

- `external_url`, `documentation.url` — mesh-routing dependent
- `environment`, `full_name` — deployment identity
- `glossary` — read off a running product's filesystem
- per-port `infra_profile_name` — resolved live against an infra profile

Absent and `null` mean different things here. A `null` (like `info.description`)
means *the manifest did not say*. An absent key means *this surface cannot
know*. Never report a missing live field as empty, unset, or unconfigured —
say the artifact surface doesn't carry it.

Optional fields that the projection does carry always serialize (as `null` when
empty); collections always serialize, empty as `[]`.

## Reading `outputs` without the union trap

Top-level `model_names` lists models declared at the **output level only**. It
is **not** a union across ports.

A product that declares its models under each port — the common shape — reports
an **empty** top-level `model_names` and populated per-port lists. Reading only
the top level and concluding "this product exposes no models" is wrong.

To enumerate what a product actually exposes, walk `ports[].model_names` (and
union them yourself if you need a flat list). This mirrors exactly what a
deployed product reports for the same manifest, which is why the projection
refuses to union on your behalf.

## Static artifact lifecycle

After build or resume, `nxd-render-static-artifact` reads `current`, then the exact
release `verified.json` and `outputs`, validates one matching release bundle,
and writes a self-contained HTML file before `describe_models` or any query.
It fails whole on a missing or mismatched read.
`list_data_products` is discovery only and never fills a release-document gap.
After a same-workflow rebuild, discard cached resource URIs and rerender the
new sequence; the older file is historical.

It reads those documents through the resource operations when the client
exposes them, and through the two bridge tools above when it does not — one
transport for the whole bundle either way. No other tool may supply artifact
content.

## When a read fails

- **`resource_not_found` naming a newer `current_publish_seq`** — the release
  was superseded. Re-read `current` (or `resources/list`) and retry against the
  current seq. Not an error state; a rebuild happened.
- **`artifact_unavailable`** — the published data was garbage-collected or
  failed integrity checks. The server marks this **not retryable**: rebuild with
  `build_data_product` from the source definition. Re-reading won't help.
- **`workflow_not_found`** — nothing published under that workflow. The error
  carries `available_workflows`; `list_data_products` shows what exists, or
  `build_data_product` creates a new product.

Report a read failure as what it is. Never substitute a shape inferred from the
source definition for a resource read and present it as the published product.
