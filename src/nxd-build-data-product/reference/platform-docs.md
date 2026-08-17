# Platform docs reference

Hand out **user-facing platform docs only** — the app UI, the served docs
site, and the public CLI / REST / MCP surfaces. **Never** link internal
repos, wikis, design docs, or anything not reachable from the user's own
mesh. When in doubt, prefer a tool you can run over a page you'd link.

Link **liberally and contextually**: when a user is stuck on or asking about
a specific step (inputs, outputs, scheduling, MCP, etc.), drop the matching
doc link inline rather than waiting to be asked. Always offer to go deeper or
to **demonstrate live with the CLI** instead of just pointing at a page.

## Resolving the docs base

Docs are served **per-mesh**, from the active mesh's app host. There is no
single global docs URL — the host is whatever app the user's selected mesh
points at.

Resolve it from the user's mesh config, do not hardcode it:

1. Read `~/.nxd/meshes.json`.
2. Find the **selected / active** mesh entry.
3. Take its `app_url` (e.g. `https://app.demo.trynxd.com` — this is only an
   example; use whatever the config actually has).

The docs base is then:

```
<app_url>/docs/#/
```

and any specific page is:

```
<app_url>/docs/#/<path>
```

Notes:

- The docs site is **docsify** with **hash (`#/`) routing** — the `#/` is
  required, and paths after it are routed client-side. Append the path
  **without** a `.md` extension.
- If a deep link **404s or shows a blank page, do not guess** alternate
  paths. Instead:
  - open the docs **home** (`<app_url>/docs/#/`) and navigate from its
    sidebar, or
  - use the **in-app Learn tab**, or
  - re-confirm the host by re-reading the user's mesh config — a stale or
    wrong `app_url` is the most common cause.

## Canonical doc paths

Append each path to `<app_url>/docs/#/`. No `.md` extension.

| Topic | Path to append to `<app_url>/docs/#/` | Hand out when |
|---|---|---|
| Orientation / docs index | `tutorials/guides/README` | First contact; "where do I start", "what is this" |
| Quick start | `tutorials/guides/quick-start` | User wants the fastest path to a working data product |
| Getting started | `tutorials/guides/getting-started` | User wants the fuller, guided walkthrough |
| CLI setup (install / env) | `tutorials/cli/setup` | Installing `nxd`, configuring a mesh, auth/PAT setup |
| Create a data product (CLI) | `tutorials/cli/create` | Scaffolding a new data product from the CLI |
| Semantic model | `tutorials/guides/01-semantic-model` | Defining the semantic model / entities / fields |
| Inputs | `tutorials/guides/04-inputs` | Wiring source inputs into a data product |
| Outputs | `tutorials/guides/02-outputs` | Defining output ports / consumable outputs |
| Promises & data quality | `tutorials/guides/03-promises` + `tutorials/cli/data_quality` | Declaring promises; checking/enforcing data quality |
| Expectations | `tutorials/guides/05-expectations` | Adding expectations / validation rules |
| Scheduling | `tutorials/guides/06-scheduling` | Setting run cadence / schedules |
| MCP | `tutorials/guides/07-mcp` | Exposing or consuming a data product via MCP |
| Consuming other data products | `tutorials/guides/consumer-tutorial` | Reading/depending on another team's data product |

## The platform itself is a doc

Often the best "documentation" is the live state of the user's own mesh —
prefer it over prose when it answers the question:

- **`nxd ls data-products`** — the authoritative list of what exists in the
  active mesh, with current state. Great for "what's already here" and for
  grounding an answer in real names instead of placeholders.
- **App catalog / product page** — `<app_url>/app/data-products/<name>` for a
  specific data product (resolve `<app_url>` exactly as above). The catalog
  view at `<app_url>/app/data-products` lists everything browsable.
- **In-app Learn tab** — the docs surfaced inside the app, always matched to
  the running mesh; a reliable fallback when a deep doc link doesn't resolve.

## Tools over external refs

When you can **show** instead of **link**, show. Prefer:

- the **`nxd` CLI** — run the command and read back the real output;
- the **REST API** — authenticated with a PAT via the
  `x-nextdata-token: <PAT>` header (or `Authorization: Bearer` on
  multi-domain environments);
- **MCP** — drive the data product's MCP surface directly.

A live CLI/REST/MCP demonstration against the user's actual mesh is almost
always more useful than pointing at a manual page — use the doc links above
to orient and to fill gaps, not as a substitute for doing the thing.
