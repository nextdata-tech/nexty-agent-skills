# Contextual links

**Only hand out user-facing platform docs.** The learner has access to the argenx platform
docs site and the nxd CLI / REST API / MCP tools — nothing else (no internal repos, no source).
Do not link to GitHub repos, internal wikis, or anything behind employee auth.

> The docs base URL is environment-specific. On the argenx environment it is
> `https://docs.argenx.nextopia.dev`. If the learner is on a different environment, swap the
> host but keep the same `#/...` paths. Confirm the host from their mesh/`nxd-setup` config.

## Canonical doc links (argenx environment)

| Topic | Link | Hand out when |
|---|---|---|
| Tutorials index (foundations) | `https://docs.argenx.nextopia.dev/#/tutorials/guides/README` | Step 0, for the curious |
| Local setup | `https://docs.argenx.nextopia.dev/#/tutorials/cli/setup` | Step 1 / 2, env or install questions |
| Create a data product | `https://docs.argenx.nextopia.dev/#/tutorials/cli/create` | Step 3 |
| Semantic model | `https://docs.argenx.nextopia.dev/#/tutorials/guides/01-semantic-model` | Step 4, output models |

> These paths come from the argenx EDP guide. If a path 404s, fall back to the tutorials index
> and navigate from there rather than guessing a URL.

## The platform itself as a "doc"

The learner can *see* what they built — often more convincing than prose:
- `nxd ls data-products` — confirm it's live (Step 6).
- The data catalog / product page in the platform UI — show the deployed product, its models,
  and lineage. Get the URL from the mesh config or the platform home page.

## Tools the learner has (use these instead of external references)

- **nxd CLI** — `nxd ls ...`, `nxd describe ...`, `nxd validate`, `nxd launch`. Prefer
  demonstrating with these over linking to a manual.
- **NXD REST API** — `GET /api/v1/...` with the `x-nextdata-token` header (the PAT from the
  mesh config). Use for things the CLI doesn't expose (e.g. infra-profile services).
- **MCP tools** — if the environment exposes an `mcp-api`, a deployed product's read-only
  tools can be called directly; useful to *show* the learner their product answering queries.

When the learner asks "where can I read more about X?", point at the relevant doc above **and**
offer to demonstrate it live with the CLI — showing beats reading for this audience.
