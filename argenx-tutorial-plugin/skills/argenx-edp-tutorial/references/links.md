# Contextual links

**Only hand out user-facing platform docs + the in-app Learn section.** The learner has the
argenx platform (app + docs + CLI/REST/MCP) — nothing else (no internal repos, no source). Do
not link to GitHub repos, internal wikis, or anything behind employee auth.

Link **liberally and contextually**, and always **offer to go deeper**: after any step, say
*"Want me to explain that more, or show you the doc?"* — this audience learns by having the
option, not by being forced through a manual.

## Doc base for the argenx environment

```
https://nxd.aks.argenx-dev.com/docs/#/
```

This is a **single-domain** environment — everything lives under the one host:
- App / catalog: `https://nxd.aks.argenx-dev.com/app/...`
- REST API:      `https://nxd.aks.argenx-dev.com/api/v1/...`
- Docs:          `https://nxd.aks.argenx-dev.com/docs/#/...`

> Docs are served with docsify, so routes are hash paths: `.../docs/#/<path-without-.md>`.
> If a deep link 404s, don't guess — open the docs home and navigate, or use the **Learn** tab
> inside the app (left sidebar). Confirm the host from the learner's mesh config if they're on a
> different environment; keep the same `#/...` paths.

## Canonical doc links (verified route paths)

| Topic | Path (append to the docs base) | Hand out when |
|---|---|---|
| Tutorials index | `tutorials/guides/README` | Step 0, orientation |
| Quick start | `tutorials/guides/quick-start` | Step 0/1, the impatient learner |
| Getting started | `tutorials/guides/getting-started` | Step 0, the careful learner |
| Local setup (CLI) | `tutorials/cli/setup` | Steps 1–2, install / env questions |
| Create a data product | `tutorials/cli/create` | Step 3 |
| Semantic models | `tutorials/guides/01-semantic-model` | Step 4, output models |
| Inputs | `tutorials/guides/04-inputs` | Step 4, input models |
| Outputs | `tutorials/guides/02-outputs` | Step 4/6, output ports |
| Promises / data quality | `tutorials/guides/03-promises`, `tutorials/cli/data_quality` | Step 8, quality checks |
| Expectations | `tutorials/guides/05-expectations` | Step 8 |
| Scheduling | `tutorials/guides/06-scheduling` | Step 4, the `schedule=` cron |
| MCP | `tutorials/guides/07-mcp` | Step 7, Claude Desktop wiring |
| Consuming other DPs | `tutorials/guides/consumer-tutorial` | Step 8, Alation-as-reference |

Example, full URL for "create":
`https://nxd.aks.argenx-dev.com/docs/#/tutorials/cli/create`

## The platform itself as a "doc"

The learner can *see* what they built — often more convincing than prose:
- `nxd ls data-products` — confirm it's live (Step 6).
- The **catalog / product page** in the app (`.../app/data-products/<name>`) — shows the deployed
  product, its models, attributes, inputs/outputs, lineage graph, and a trust summary. A real
  example on this env is the `open-meteo-loader` DP (a public-API → Snowflake source-aligned DP,
  WEATHER/INGESTION domain) — a close, friendly analog to what the learner is building.
- The **Learn** tab in the app sidebar — in-product tutorials.

## Tools the learner has (prefer these over external references)

- **nxd CLI** — `nxd ls ...`, `nxd describe ...`, `nxd validate`, `nxd launch`, `nxd mcp config`.
  Demonstrate live rather than linking to a manual.
- **NXD REST API** — `GET https://nxd.aks.argenx-dev.com/api/v1/...` with the `x-nextdata-token`
  header (the PAT from the mesh config). For what the CLI doesn't expose (infra-profile services).
- **MCP tools** — a deployed product's read-only tools (see Step 7); useful to *show* the learner
  their product answering questions in Claude Desktop.

When the learner asks "where can I read more about X?", give the relevant doc above **and** offer
to demonstrate it live with the CLI — showing beats reading for this audience.
