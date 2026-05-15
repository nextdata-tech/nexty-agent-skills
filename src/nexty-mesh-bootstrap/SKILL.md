---
name: nexty-mesh-bootstrap
description: Artifact-led migration accelerator for discovering enterprise data assets and drafting a first Nextdata mesh. Use when Codex needs to inventory source systems, Snowflake assets, Git repositories, local files, PDFs, PowerPoints, diagrams, images, BI/report context, identity/role exports, and team/domain structure, then propose future-state data products and generate validate-ready local draft specs without launching them.
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
metadata:
  author: nextdata
  version: 0.2.0
---

# Nexty Mesh Bootstrap

Use this skill to help a user get the lay of the land quickly and create a first version of a Nextdata mesh. Treat the workflow like a migration accelerator: collect source evidence, normalize it into an inventory, propose product boundaries, generate local draft data products, and validate locally. Do not launch or deploy anything.

Default run output directory:

```bash
.context/mesh-bootstrap/<YYYYMMDD-HHMMSS>/
```

Required run artifacts:

- `state.json` — phase checkpoint for resume
- `open-todos.md` — running ledger of unresolved questions and missing artifacts
- `mesh-inventory.json`
- `domain-map.md`
- `cloud-footprint.md`
- `identity-map.md`
- `mesh-map.md`
- `product-candidates.md`
- `draft-products/<product-name>/`

## Workflow

Run these phases in order. Keep the workflow artifact-led: a live mesh may provide setup, permissions, infra profiles, glossaries, and validation context, but the target mesh may be empty.

The wizard is **multi-session and resumable**. After every phase, write `state.json` and update `open-todos.md`. On re-invocation, see `references/state-and-resume.md` for the resume protocol — load the latest run, replay state, and let the user revisit any phase.

At any point, the user may say "TODO: come back to <X>" or "I don't have <Y> handy". Append a row to `open-todos.md` (`{phase, item, blocker, owner, added_at}`) and continue with a placeholder. Never block the wizard on missing artifacts — record and move on.

### 1. Prepare the workspace

Create a timestamped run directory under `.context/mesh-bootstrap/`. Initialize `state.json` (`{run, phase: "prepare", completed: []}`) and an empty `open-todos.md`.

If the user wants live mesh validation or infra context, use the existing `nxd-setup` skill first. Reuse its active `--config /tmp/nxd-<mesh_name>.yaml` for all `nxd` commands. If no mesh is available, continue in blueprint mode and mark validation that depends on the mesh as skipped.

Never depend on `nxd ls data-products` to discover the existing estate. Existing data products may be absent or incomplete.

If `.context/mesh-bootstrap/` already contains prior runs, surface the latest and ask: "Resume the run from `<timestamp>` (last phase: `<phase>`), or start fresh?" If resume, load `state.json`, `mesh-inventory.json`, and `open-todos.md`, then jump to the next incomplete phase.

### 2. Domain & subdomain intake

Goal: produce `domain-map.md` and an authoritative `domains` array in `mesh-inventory.json`. Domains drive product ownership, infra-profile boundaries, and downstream candidate clustering.

Ask: "Do you have a domain map (image, PDF, slide deck, markdown table) the business has already published?"

- **File provided** — read it. Images (PNG/JPG) and PDFs go through the `Read` tool's multimodal path; markdown tables go through `Read` + `Grep`. Extract a tree of `{domain → [subdomains]}`. Confirm with the user before continuing.
- **No file** — fall back to Q&A: walk the user through naming top-level domains, then subdomains under each. Suggest common shapes (Research / Development / Commercial / TechOps / G&A) only if the user is stuck.
- **Partial knowledge** — record what is known, append `TODO(domains)` rows to `open-todos.md` for the gaps, continue.

Each domain entry must record `{name, parent, evidence, confidence, owner_team, notes}`. Examples and templates live in `references/domain-map-intake.md`.

### 3. Cloud footprint & accounts

Goal: produce `cloud-footprint.md` and a `cloud_footprint` array in `mesh-inventory.json`. This is the **primary input for proposing infra profiles per (domain × cloud) pair** in Phase 7.

Ask: "Do you have an Enterprise Architecture or Data Platform Assessment doc that lists clouds, platforms, and account counts?"

- **File provided** (markdown, PDF, slides) — read it. Extract platforms (Snowflake, Databricks, Fabric, S3, ADLS, GCS, BigQuery, Redshift, etc.), per platform: `{clouds, regions, account_count, env_split, owner_domain, notes}`. Example to mirror: argenx DAP assessment lists eight Snowflake accounts split across DDQ Dev/Test/Prod (Azure + AWS) and Commercial Prod/Non-prod.
- **No file** — Q&A. For each platform the user names, ask for clouds → regions → account count → env naming → owner domain. One platform at a time.
- **Partial** — record the platforms the user remembers, mark unknowns as `TODO(cloud-footprint)`, continue. The wizard re-asks on resume.

Use the resulting matrix to **propose infra profiles**: one profile per `(domain, primary cloud)` pair, plus shared profiles for cross-domain platforms. Surface the proposed profile list at the end of this phase for confirmation. Templates and an example matrix live in `references/cloud-footprint-intake.md`.

### 4. Identity & role mining

Goal: produce `identity-map.md` and an `identities` array in `mesh-inventory.json`. Identities ground product ownership, stewardship, and consumer-access decisions; role groupings often validate or correct domain boundaries from Phase 2.

Inspired by Okta-to-Entra companion-tool exports and SailPoint-style role mining: the wizard ingests IdP/role data when available and falls back to Q&A otherwise.

Ask: "Do you have an IdP export — Okta CSV, Entra ID `Get-MgUser`/`Get-MgGroup` output, AD group dump, SailPoint role definitions, or an HR roster?"

- **File provided** — read it. Extract `{identities, groups, roles, group_memberships, app_assignments}`. Look for naming conventions that map to domains (e.g. `dap-research-prod-readers` → domain `Research`).
- **No file** — Q&A. Collect: producer teams per domain, stewards per domain, top consumers per domain, compliance reviewers. Map each to a placeholder identity record.
- **Partial** — record what's known; `TODO(identity)` for gaps.

Cluster identities into candidate roles using a simple role-mining heuristic: groups whose members and app-access patterns overlap above a threshold are the same logical role. Reconcile clusters against the domain tree from Phase 2 — flag mismatches in `identity-map.md`. Templates and the heuristic live in `references/identity-mining.md`.

### 5. Collect discovery inputs

Ask for or inspect all available sources:

- Snowflake accounts, databases, schemas, tables, views, stages, tasks, streams, query history exports, and warehouse usage notes.
- Git repositories with SQL, dbt, Spark, Airflow, notebooks, orchestration configs, tests, manifests, and documentation.
- Local or remote files such as CSV, JSON, JSONL, Parquet, Avro, Excel, logs, exports, and samples.
- PDFs, PowerPoints, diagrams, screenshots, architecture docs, data dictionaries, BI catalogs, report screenshots, and team/domain documents.
- Stakeholder context: domains, owners, stewards, source-system teams, consuming teams, critical reports, SLAs, compliance constraints, and known pain points.

Use `references/discovery-guide.md` for concrete prompts and source-specific handling rules.

### 6. Normalize the inventory

Build `mesh-inventory.json` using `references/inventory-schema.md`. Merge in the artifacts from Phases 2–4 (`domains`, `cloud_footprint`, `identities`) so the inventory is the single source of truth. Every inferred fact must carry evidence and confidence:

- Use `high` confidence for direct schemas, source code, command output, or exact user confirmation.
- Use `medium` confidence for repeated naming patterns, diagrams that align with other evidence, or report/source matches.
- Use `low` confidence for single mentions, screenshots, visual-only inference, or plausible but unconfirmed grouping.

For local CSV, JSON, JSONL, or Parquet samples, run:

```bash
python3 src/nexty-mesh-bootstrap/scripts/profile_tabular.py <path>
```

The script prints a schema/sample profile as JSON and does not write files.

### 7. Propose the mesh map and infra profiles

Write `mesh-map.md` as a readable current-state and future-state map:

- Current assets by source system, repo, document set, domain, and team.
- Data flows, dependencies, freshness hints, consumers, reports, and transformation jobs.
- Candidate domain boundaries (pre-filled from Phase 2) and ownership assumptions (pre-filled from Phase 4).
- **Proposed infra profiles** — one per `(domain, primary cloud)` pair from Phase 3, plus shared profiles for cross-domain platforms. Surface this list and confirm with the user before Phase 8.
- Gaps, blockers, access needs, and unresolved questions (pull open rows from `open-todos.md`).

Use `references/accelerator-workflow.md` for the migration-accelerator pattern.

### 8. Select product candidates

Write `product-candidates.md` with ranked product proposals. For each proposal include:

- Product name, type, proposed domain, owner/steward, and purpose.
- Source evidence and confidence.
- Inputs, outputs, dependencies, consumers, freshness, scheduler hints, and quality expectations.
- Why it is in the first wave or deferred.
- Missing information and validation status.

Use these product types:

- `source-aligned`: preserves source shape and exposes raw or lightly standardized source assets.
- `domain`: models business-owned concepts and transformations.
- `aggregate`: composes multiple products into analytics-ready outputs.
- `serving`: supports a report, app, API, ML, or agent consumption path.
- `context-document`: wraps unstructured documents, diagrams, policies, or knowledge assets.

Default to source-aligned products when discovering raw systems. Propose curated/domain products only when there is evidence of transformations, reports, repeated consumption, business concepts, or ownership.

### 9. Generate validate-ready draft products

After the user selects first-wave candidates, generate local drafts under `draft-products/<product-name>/`. Use the closest examples from `nextdata-tech/nextdata-public-examples`; see `references/examples-guide.md`.

Each draft product must include:

- `spec.py`, `transform.py`, `requirements.txt`, and model/import files consistent with the repo's `nexty-bootstrap` skill patterns.
- Domain, infra profile, compute service, output storage, semantic models, input/output ports, and scheduler hints where known.
- Clear TODOs for missing credentials, unresolved access, uncertain schema fields, or unconfirmed owners.
- Source evidence comments or adjacent notes linking each generated model and product decision back to `mesh-inventory.json`.

Preserve source shape for source-aligned products. Each infra service should become a separate input when it represents a distinct source. Each unique schema should have its own semantic model. Add model schema promises and input expectations when the data shape is known.

If time partitions are evident, propose matching schedules and freshness checks. If not partitioned, ask the user to confirm the refresh pattern before finalizing schedules.

### 10. Validate without launch

Run only local or read-only validation:

```bash
python3 -m compileall .context/mesh-bootstrap/<timestamp>/draft-products
```

If a live mesh is configured and `nxd` supports local validation, run the available validation command against each draft directory. Do not run launch/deploy commands.

Before completing, verify every draft product has:

- Domain and owner/steward assumptions.
- Infra profile, compute service, and output storage decisions or TODOs.
- Semantic models with field types and descriptions where evidence exists.
- Input/output mapping, freshness expectation, and quality notes.
- Evidence and confidence recorded in `mesh-inventory.json`.

## Source Handling Rules

Read `references/discovery-guide.md` when discovering assets. Apply these defaults:

- Snowflake discovery is read-only: collect metadata, descriptions, schemas, row counts where feasible, lineage clues, query/task hints, and user-provided business context. Do not mutate objects.
- Git discovery is read-only: inspect code, manifests, configs, tests, and docs. Do not run repo commands that change files.
- Unstructured discovery should extract useful text and visual context, but record uncertainty. Do not treat diagrams, screenshots, or slide labels as authoritative without corroborating evidence.
- Live mesh access is optional. Use it for infra, role, glossary, and validation context only.

## References

- `references/accelerator-workflow.md`: migration accelerator pattern for this skill.
- `references/domain-map-intake.md`: Phase 2 file/Q&A protocol and templates.
- `references/cloud-footprint-intake.md`: Phase 3 platform/account matrix and infra-profile proposal rules.
- `references/identity-mining.md`: Phase 4 IdP ingest, role-mining heuristic, domain-boundary reconciliation.
- `references/state-and-resume.md`: `state.json` schema, resume protocol, open-TODO ledger format.
- `references/discovery-guide.md`: prompts and artifact handling rules.
- `references/inventory-schema.md`: required inventory and candidate structures.
- `references/examples-guide.md`: how to use public Nextdata examples.
