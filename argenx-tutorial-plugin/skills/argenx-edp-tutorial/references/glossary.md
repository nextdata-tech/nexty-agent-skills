# Glossary — plain-language definitions

Give these *just in time*, the first time a term appears — one sentence, no jargon stacking.
Never front-load the whole list on the learner.

- **Data product** — a small, self-contained package that pulls data from a source, lands it
  somewhere useful, and makes it discoverable, governed, and shareable. The thing we're building.

- **Mesh** — the argenx Nextdata environment your CLI is connected to (think: "the server").
  You may have more than one (e.g. dev vs production); the setup step picks which.

- **nxd CLI** — the `nxd` command-line tool you use to create, validate, and deploy data
  products. On the argenx VDI it runs inside WSL (see `windows-wsl.md`).

- **Infra profile** — a named bundle of credentials and services (Snowflake, an API, storage…)
  that a data product is allowed to use. You pick one; the platform injects the secrets so you
  never paste them yourself.

- **Service** — one entry inside an infra profile (e.g. a Snowflake connection, a Salesforce
  API). Inputs and outputs point at services by name.

- **Input** — where a data product reads data from. Named in the spec; available in the
  transform under the same name (hyphens become underscores).

- **Output / port** — where a data product writes its results (e.g. a Snowflake schema). Also
  what other people connect to when they consume your product.

- **Semantic model** — the described shape of your data: named, typed fields with descriptions.
  This is what turns a raw table into something discoverable and governed.

- **Schema** — (two meanings, clarify by context) ① the set of typed fields in a semantic
  model; ② in Snowflake, the named container that holds your output tables.

- **Transform** — the one Python function that does the actual work: it receives your inputs
  and outputs by name and you write the logic in between.

- **EDP library** (`edp/`) — the argenx-specific helper code that hides repetitive plumbing,
  so you only fill in the interesting parts. It comes with the template.

- **Template** — a published, ready-to-edit starting point for a data product. `nxd create
  data-product --template ...` scaffolds your project from it, EDP library included.

- **Schedule (cron)** — how often the transform runs, written as a cron expression.
  `*/20 * * * *` means "every 20 minutes." `0 * * * *` is hourly; `0 0 * * *` is daily.

- **Validate** — `nxd validate` checks your data product makes sense *before* deploying.
  Reading its errors is the best way to learn.

- **Launch / deploy** — `nxd launch` puts your data product live on the argenx environment.

- **Provisioning** — infrastructure setup (creating tables, integrations) that the platform
  can do automatically before your transform runs. The advanced reference DP uses "deferred
  provisioning"; the tutorial DP doesn't need to.
