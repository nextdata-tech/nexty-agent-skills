---
name: nxd-analyze-mesh
description: Inspect data-bearing services in a Nextdata OS infra profile to discover candidate data product inputs and outputs. Reads an infra profile file, connects read-only to S3, Snowflake and ADLS — the three service types with shipped inspection drivers — inventories files/tables/schemas, and reports data sources that appear connected as a source-aligned data product. Other declared data-bearing services (Databricks, BigQuery, Postgres, Kafka, Pinecone, and more) are classified and reported as unsupported rather than inspected. Use when discovering candidate data products from infra profiles, mesh assets, service schemas, or offline evidence.
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - AskUserQuestion
metadata:
  author: nextdata
  version: 0.36.0
---

# Nexty Mesh Assets

Discover candidate data product **inputs and outputs** by inspecting the live services declared in a nextdata infra profile.

Given an infra profile file, this skill connects to the data-bearing services it lists, inventories their contents (directories, files, schemas, tables), and reports the data sources that appear **connected** — where one source looks like the input to another. The result is a list of candidate data products, each with its inputs, outputs, and a source-aligned vs. transformed classification.

## Concepts

- **Data asset** — a discrete source of data: a file or directory on file-based storage (S3, ADLS), or a table/topic/index in database storage (Snowflake, Databricks, BigQuery, Postgres, Kafka, Pinecone).
- **Input / output** — an asset consumed by a transform (input) or produced by one (output). The same asset can be the output of one product and the input of another.
- **Transform** — a function that runs on one or more inputs to produce one or more outputs.
- **Connected** — two assets belong to the same candidate data product when one appears to feed the other: similar schema, related naming, matching partitioning, and output written after input.
- **Source-aligned data product** — reads from one source and writes to another with *minimal transformation*, keeping a near-identical data model (rename, reformat, repartition — not reshape). Contrast with a *transformed* product that aggregates, joins, or restructures.

This skill discovers candidates only — it does not generate data product specs. Hand the results to **nxd-build-data-product** to scaffold a data product.

---

## Platform docs

Docs are served **per-mesh** from the active mesh's app host — there is no single global docs URL. Resolve the base from `~/.nxd/meshes.json`: read the **selected / active** mesh entry and take its `app_url`. Doc pages are then `<app_url>/docs/#/<path>` (docsify hash routing — keep the `#/`, append the path with no `.md` extension). If a deep link 404s or shows a blank page, do not guess paths — open the docs home `<app_url>/docs/#/` and navigate the sidebar, or re-confirm `app_url` from the mesh config.

Hand out these paths inline when the matching step comes up (drop the link at the step, don't wait to be asked):

| Topic | Path (append to `<app_url>/docs/#/`) | Surface at |
|---|---|---|
| Getting started | `tutorials/guides/getting-started` | Step 1 — no profile/active mesh found; orient the user |
| Inputs | `tutorials/guides/04-inputs` | Step 4 — one-service-one-input / one-schema-one-model convention |
| Outputs | `tutorials/guides/02-outputs` | Step 5/6 — source-aligned vs transformed output classification |
| Semantic model | `tutorials/guides/01-semantic-model` | Step 6 — how inferred schemas become input/output models |
| Scheduling | `tutorials/guides/06-scheduling` | Step 6 — mapping partition granularity to a transform `when` |
| Create a DP (CLI) | `tutorials/cli/create` | Closing handoff to nxd-build-data-product |

`app_url` is owned by nxd-setup-cli, which persists it in the nxd registry and writes the active session config to `<session_config>` (`/tmp/...` on POSIX/WSL, `$env:TEMP\...` on Windows PowerShell). Prefer **showing** live state (`nxd ls data-products`, `nxd ls infra-profiles`) over linking a page when it answers the question.

---

## Scripts

The skill ships a small Python package under `scripts/`. **First make it
reachable from Bash:** some harnesses mount only docs + `SKILL.md` into the shell
the Bash tool runs in, so `scripts/` (with its `drivers/` + `meshlib/` subpackages)
can be absent even though the skill loaded — then every `python scripts/...` call
fails with a *shell* "No such file or directory". Resolve a `WORKDIR` **once per
session** (skill dir if Bash sees its scripts, else a scratch copy that preserves
the package layout), then run all entrypoints + the venv from `$WORKDIR`. Recipe
(probe → Glob/Read/Write copy → confirm) + rationale:
**[reference/scripts-bootstrap.md](reference/scripts-bootstrap.md)** — read it
first. Quick probe:

```bash
[ -f "$SKILL_DIR/scripts/classify_profile.py" ] && WORKDIR="$SKILL_DIR"   # else bootstrap a copy
```

Then install the dependencies from `scripts/requirements.txt` into a throwaway venv
(Windows: `py -3 -m venv` + `.\...\Scripts\pip.exe`):

```bash
python3 -m venv .nxd-analyze-mesh-venv
.nxd-analyze-mesh-venv/bin/pip install -r "$WORKDIR/scripts/requirements.txt"
```

**Entrypoints** (run as `python "$WORKDIR/scripts/<name>.py"`):

| Script | Purpose |
|---|---|
| `classify_profile.py <profile>` | Parse the profile, classify every service, list the inspectable (Storage/API) ones. |
| `inspect_service.py <profile> <service>... --out FILE` | Connect read-only, inventory each service with schema-fingerprint grouping, de-duplicate shared stores, write inventory JSON. |
| `match_assets.py <inventory.json>... [--flow SRC:DST]` | Match candidate input/output pairs, classify, and write the report + models markdown. `--flow` (repeatable) scopes matching to declared architecture flows. |
| `profile_tabular.py <path>` / `profile_tabular.py <db.duckdb> <table>...` | Read-only local profiler. File mode: CSV/JSON/JSONL/Parquet sources that aren't live services. DuckDB mode: materialized `main.<table>` tables (e.g. a dlt sample load), enriched with exact full-table nullability/cardinality; two or more tables emit ONE combined document (redirect to `schema.json` as the profiling→inference handoff artifact). Prints an inferred schema (types, nullability, sample values, partition/freshness hints) as JSON. Used by the offline discovery pass and by nxd-build-semantic-data-product's Step 1-alt. |

**Layout** — service-type code is isolated from generic code:

- `scripts/meshlib/` — generic core: profile parsing, schema-fingerprint grouping, the plugin registry, inspection orchestration, matching, report writing. Imports **no** service SDK.
- `scripts/drivers/` — one module per service type (`s3.py`, `snowflake.py`), each owning its SDK imports (boto3, snowflake-connector) and any per-source-type rules. An entrypoint builds a registry from these and injects it into `meshlib`.

To support another service type, add `scripts/drivers/<name>.py` exposing a `DRIVER` (see `meshlib/registry.py` and the recipes in `reference/service-inspection.md`), then add it to `ALL` in `drivers/__init__.py`. The scripts read credentials from the profile in-process and never print secret values.

---

## Customer extension paths

This skill ships generically to many customer environments. Environment-specific inputs — infra profiles and user documentation — live in **customer-owned paths outside the skill**, so they survive skill updates (an update overwrites the skill directory, never these paths):

- `./.nxd/skills/nxd-analyze-mesh/` — per-project, in the working tree
- `~/.nxd/skills/nxd-analyze-mesh/` — per-machine / per-environment

Step 1 searches both paths. Each may hold:

- **infra profile files** — a `kind: Profile` YAML, used directly
- **user documentation** — `.md` / `.txt` describing the customer's domains, naming conventions, glossary, or which services matter
- **pointer files** — a file whose contents are filesystem path(s) or URI(s), one per line; resolve each pointer to the real infra profile or document (fetch `http(s)://` URIs, read file paths)

The skill only reads these paths — never writes to them.

---

## Flow

Run the steps in order. Inspect read-only at every step — never create, write, or delete data on a service.

**Consult the user.** The person running this skill has domain knowledge of their environment. When a decision is genuinely ambiguous — which catalog owns a table, which copy of a replicated dataset is the source of truth, which of two services is the input — ask them rather than guessing.

**Offline mode.** When live inspection is not possible (no network to the services, credentials withheld, or the user prefers to share evidence by hand), run an optional read-only collection pass instead of (or alongside) live inspection — Snowflake `SHOW`/`DESCRIBE` output, Git repo inspection, and local file profiling via `scripts/profile_tabular.py`. The evidence feeds the same candidate-matching (Step 5) and lands in the same `mesh-assets-<profile>.md` report. See [reference/offline-discovery.md](reference/offline-discovery.md).

### Step 0: Resolve the active mesh (do this first)

This skill is **mesh-aware** — the mesh determines the app/api host that anchors every service URL in the report, the doc base for the links above, and which infra profiles / data products exist. Resolve it **before** anything else; do not leave the host as an unstated assumption that downstream consumers must guess.

1. Read `~/.nxd/meshes.json` and find the **selected / active** mesh entry. From it derive:
   - `app_url` — the UI / docs base (`<app_url>/docs/#/<path>`); record which mesh this run belongs to.
   - `api_url` — the base host for absolute infra-profile service URLs (feeds `--api-url`, Step 6).
2. nxd-setup-cli owns this registry and writes the active session config to `<session_config>`. If that file is present, pass `--config <session_config>` to any `nxd` command below.
3. **If no active mesh / no `meshes.json`:** point the user at **nxd-setup-cli** to select and configure a mesh first, and link `<app_url>/docs/#/tutorials/cli/setup` (or `getting-started`) if you can resolve any `app_url`. Discovery against a real mesh cannot run until a mesh is selected. The skill can still run in **offline mode** on local files (Step 1b / offline-discovery) with service URLs left relative.

Carry `api_url` and `app_url` through the whole run. Never substitute a demo host (e.g. `app.<mesh>.example`) for the real one — those forms below are **illustrative placeholders only**, not canonical hosts.

### Step 1: Locate inputs — infra profile and user documentation

Gather two inputs. For each, search the **customer extension paths** above plus the working tree, resolve any pointer files, and also let the user supply a path or URI directly at the prompt.

#### Step 1a: Infra profile

An infra profile belongs to a mesh — prefer **deriving** the available profiles from the active mesh (Step 0) over relying only on locally-globbed files, so a fresh environment with no local profile file does not dead-end.

Search / derive, in order:

1. **Derive from the active mesh** — enumerate profiles with `nxd ls infra-profiles` (pass `--config <session_config>` if present). Let the user pick one; pull its YAML to an OS temp path such as `$TMPDIR/nxd-analyze-mesh/` on POSIX/WSL or `$env:TEMP\nxd-analyze-mesh\` on Windows PowerShell.
2. The customer extension paths — `./.nxd/skills/nxd-analyze-mesh/` and `~/.nxd/skills/nxd-analyze-mesh/`.
3. The working tree — Glob `infra-profiles/*.yaml`, `infra-profiles/*.yml`, `*.yaml`, `*.yml`.

For each candidate: an infra profile file has `kind: Profile` and `apiVersion: infra.nextdata.com/...` near the top — confirm with Grep. A **pointer file** (contents are a path or URI) is followed to the real profile — fetch `http(s)://` URIs, read file paths.

Present every candidate found (from the mesh and from local paths) and let the user confirm which to use — or paste a path/URI of their own. Read the chosen file. If neither the mesh nor local paths yield a profile, link `<app_url>/docs/#/tutorials/cli/setup` and point the user at **nxd-setup-cli** to configure the mesh / extension paths before discovery can run.

#### Step 1b: User documentation

Customer-specific documentation augments the skill's generic knowledge. Gather two kinds:

- **Data dictionary / glossary** — the customer's domains, naming conventions, and glossary terms.
- **Data architecture** — which services and databases are sources versus derived, and how data flows between them. This is essential: one account (e.g. a single Snowflake account) can host several databases that are each a distinct stage of one data flow — or several unrelated systems. The skill must **not** assume two databases in one account are the same system, nor that they are unrelated — only the customer's architecture documentation, or the user, can say.

Search the customer extension paths for `.md` / `.txt` documents and pointer files (file paths or `http(s)://` URIs). Also ask the user directly: "Do you have documentation of this environment's **data architecture** — which databases/services feed which — and a data dictionary or glossary? A file path or URL is fine."

Resolve and read whatever is found or supplied. If no architecture documentation exists, say so and ask the user conversationally which services/databases feed which — a large multi-database account cannot be matched sensibly without it (Step 5). Carry the content as context: it tells the skill which service→service pairs are real flows (Step 5), informs domain classification and naming (Step 5) and the review (Step 6), and **overrides** the generic heuristics on conflict.

### Step 2: List services and let the user select

Parse the YAML. Services live under `spec.services[]`; each has `name`, `driver`, and `attributes` (a list of `{key, value}` pairs, sometimes with `public: false`).

Run `scripts/classify_profile.py <profile>` to parse and classify in one step. Classification keys off each service's `driver` (see the **Driver Classification Reference** below). Only **Storage** and **API** services hold data and can be inspected — Compute, RPC, and Governance services are not data sources and must be excluded from inspection.

Present the data-bearing services as a numbered list. For each, show the name, driver, and the non-secret locator only (e.g. S3 `bucket`, Snowflake `database`, ADLS `account_name`, BigQuery `dataset_id`). **Never display credential attributes** (access keys, secrets, passwords, tokens, PEM blocks).

**Prompt the user for which services to parse — always, never auto-select.** Use `AskUserQuestion` (multi-select). Pre-select all Storage services as the default, but the user confirms or narrows the list. Inspect only the services they choose.

**Only S3, Snowflake, and ADLS have shipped inspection drivers** (`scripts/drivers/`). A profile may declare data-bearing services this skill can classify but cannot connect to — BigQuery, Postgres, Kafka, Pinecone and the rest inventory as *unsupported*, not as empty. Say so when presenting the list, so the user does not read a missing driver as a missing dataset, and never write code mid-discovery to fill the gap.

### Step 3: Credential handling

The infra profile file contains **live credentials in plaintext**. Before inspecting:

- Tell the user the file holds real secrets and that inspection will connect to live services.
- Never echo a secret value into the chat or into a displayed command line.
- Inspect via short Python scripts that read the profile file **directly** and pass credentials in-process — do not interpolate secrets into shell command arguments (they would appear in the displayed command and tool output).
- Write inspection scripts under an OS temp path. Delete them when done.

### Step 4: Inspect each selected service

Run `scripts/inspect_service.py <profile> <service>... --out <file>` — it connects read-only, inventories each service with schema-fingerprint grouping, de-duplicates shared stores, and writes the inventory JSON. Driver plugins for `s3` and `snowflake` ship under `scripts/drivers/`; for any other driver, follow the matching per-service recipe in `reference/services/<type>.md` (indexed by `reference/service-inspection.md`) and add a new `scripts/drivers/<name>.py` module.

Build an **asset inventory** for the service. For every data asset record:

- **Locator** — full path/URI or fully-qualified table name.
- **Kind** — `file`, `directory`, `table`, `topic`, or `index`.
- **Format** — csv, parquet, json, iceberg, delta, etc.
- **Schema** — column/field names with types (infer from a file sample or `DESCRIBE`).
- **Partitioning** — partition keys or `key=value` / date-style path segments, if any.
- **Size** — object/row count and total bytes where cheap to obtain.
- **Last modified** — most recent write timestamp.

The inventory must honor the Nextdata OS **one service = one input** and **one unique schema = one input model** convention — this is what makes the results map cleanly onto nxd-build-data-product. For the model behind it, link `<app_url>/docs/#/tutorials/guides/04-inputs` (resolve `<app_url>` per Step 0 / Platform docs).

**Group file-based storage by schema fingerprint, not by directory path.** Path-based grouping fails both ways: a bucket laid out as `<data-product>/<port>/...` collapses a whole product into one asset, while a raw partitioned export explodes one dataset into one fragment per partition. Instead — infer each file's schema, then group files that share an identical schema and format into one logical asset. Path segments that *vary within a group* are **partition keys** (`key=value`, date segments, numeric ids) — record them as partitioning, do not split on them. Per the Nextdata OS convention, treat **one infra service as one input** and **each unique schema as its own input model**.

**Delta / Iceberg tables are one asset.** A Delta or Iceberg table on file storage is a single logical table, not the pile of `_delta_log/`, `metadata/`, and UUID-named data files it is made of. `inspect_service.py` detects a table root and emits one `table` asset, taking its schema from the table metadata — that metadata is the authority and it points at the underlying parquet/avro. If a table is also registered in a catalog service (Unity Catalog, Snowflake) and it is unclear which catalog owns it, ask the user.

**De-duplicate stores.** If two selected services point at the same physical store (identical `bucket`, or identical `account`+`catalog`+`schema`), inspect it once and mark the others as duplicates — don't re-scan.

The inventory can run to thousands of assets. Write it to a file under the temp dir and work from a summary — never dump raw inventory JSON into the chat.

If a connection fails (bad credentials, network, missing client library), report it and continue with the other services — don't abort the whole run.

**But carry the gap into the report.** An asset whose counterpart lives in a service that failed to connect looks exactly like an asset with no counterpart, and the report labels those "potential standalone inputs". Name every skipped or failed service in the report, and state that standalone/unmatched conclusions are provisional until those services are inspected or the user rules them out of scope. A negative conclusion drawn over a partial inventory is not a finding.

### Step 5: Match candidate inputs and outputs

**First, confirm flow directionality with the user.** Using the data-architecture documentation (Step 1b) and the actual databases, buckets, and tables discovered in Step 4, derive the candidate service→service flows. Present each to the user and have them **confirm or correct its direction** — which service is the input (source) and which is the output. Do not infer direction from naming: an `_az` / `_azure` / region / environment suffix does **not** tell you which side is upstream — only the architecture and the user do. Pass the confirmed flows as `--flow <input-service>:<output-service>` to `match_assets.py`.

Run `scripts/match_assets.py <inventory.json>` over the inventory from Step 4. It applies the heuristics in `reference/connection-matching.md` to find connected pairs:

- Drop assets and pairs that the exclusion rules reject — Snowflake clone tables, hello-world test data, same-database plural twins, bucket/account-root assets (see `reference/connection-matching.md`).
- Set aside **replicated datasets** — a dataset copied verbatim across 3+ stores. These are not an N×N grid of products; they go to a separate report section (see below).
- Pair the rest by schema similarity, related naming (`input`/`output`, `raw`/`curated`, `bronze`/`silver`/`gold`), matching asset names, partitioning carried through, and output-modified-after-input.
- Infer direction (which asset is the input, which is the output).
- Classify each candidate product as **source-aligned** (near-identical model, minimal transform; canonically file storage → database) or **transformed** (aggregated/joined/reshaped). A same-service pair is at most low-confidence source-aligned. For how these candidates feed an output model, link `<app_url>/docs/#/tutorials/guides/02-outputs`.
- Score confidence; report **high/medium** confidence pairs as candidates and list **low** confidence ones separately as "possible".

**Replicated datasets — ask the user.** The report's "Replicated Datasets" section lists each dataset that appears identically across 3+ stores. For each, prompt the user: *"`<dataset>` is replicated across [list of locations]. Which is the source of truth (the input)?"* The user has the domain knowledge to answer. Once they pick the canonical source, the source → each other location is a source-aligned candidate; record those.

**Large multi-database accounts — scope with the architecture.** When the inventory spans many services or a database with thousands of tables, pairwise matching produces a huge, noisy candidate set — many tables coincidentally share a schema. Two databases in one account are **not** auto-collapsed into one system and **not** assumed unrelated. Use the **data-architecture documentation from Step 1b** to know which service→service flows are real, then pass each as `--flow <input-service>:<output-service>` to `match_assets.py` (repeatable) — only declared flows are scored. This tames the candidate count and drops services that are not part of any flow (e.g. a platform-metadata database). If no architecture documentation exists, prompt the user — which databases feed which — before matching; do not dump an unscoped candidate list.

`match_assets.py` classifies domains and suggests names heuristically. If user documentation from Step 1b defines the customer's domains, glossary, or naming conventions, apply it: correct the heuristic domains and suggested names to match — customer documentation overrides the generic heuristic.

### Step 6: Report

`match_assets.py` writes **three** markdown files — pass `--out mesh-assets-<profile>.md`:

- **`mesh-assets-<profile>.md`** — candidate data products, **grouped by domain**. Each candidate carries: suggested data product name, domain, infra profile name, and — for both its input and its output data source — the location, the service name, and the infra-profile service URL (absolute, anchored to the active mesh's `api_url` — see **Service URLs** below); plus the source-aligned/transformed classification, confidence, and evidence. Also lists unmatched assets, duplicate services, and failed services. **Ambiguous candidates appear here in compact form — id + counts only, no variant locators** — to keep the main report readable for downstream consumers.
- **`mesh-assets-<profile>-models.md`** — the input and output model schemas (columns and types) of each candidate, kept in a separate file for readability.
- **`mesh-assets-<profile>-ambiguous.md`** — for every ambiguous candidate in the main report, the full list of input and output locator variants. The skill reads this at run-time to prompt the user; downstream skills can also load it on demand.

These three files are the deliverable a downstream data-product-authoring skill consumes.

The model schemas in `*-models.md` are what become the candidate's input/output **semantic models** downstream — link `<app_url>/docs/#/tutorials/guides/01-semantic-model` when walking the user through them.

**Domains.** Data products live in domain groups. `match_assets.py` classifies each candidate's domain heuristically from its naming; anything it cannot classify is filed under `other`. The infra profile file does not record domains authoritatively, so **derive-or-elicit** the real domain set rather than inventing `other`: prefer the customer's domains from the Step 1b user documentation; otherwise derive the vocabulary from the active mesh's existing data products (`nxd ls data-products`, with `--config <session_config>` if present) and the profile's service/namespace names. Then review the assigned domains with the user and correct any that are wrong.

**Service URLs.** A service URL has the form `infra-profile/<profile>#/services/<service>`. Its host must be **anchored to the active mesh** — pass `--api-url <api_url>` (the `api_url` derived from the active mesh in Step 0) to `inspect_service.py` so the emitted URL is absolute and points at the mesh the profile belongs to. Do **not** elicit the host blind or leave it relative: a relative ref forces downstream consumers to assume a base, which can silently mismatch the mesh. If Step 0 found no active mesh (offline run), say so explicitly in the report — the URLs are relative and must be resolved against whichever mesh the profile came from.

For time-partitioned inputs (date or `dt=`-style segments), the report records the partition keys — the partition granularity implies the transform's refresh cadence. To turn that into a transform `when`/cron downstream, link `<app_url>/docs/#/tutorials/guides/06-scheduling`.

**Ambiguous candidates — prompt the user at run-time, then generalise.** When several candidate pairs share both an input basename and an output basename (e.g. `amazon-sales.csv` → `AMAZON_SALES` showing up across many demo/dev/int-test S3 paths and pointing at one or two Snowflake tables), `match_assets.py` collapses them into a single block in the main report flagged as **`ambiguous candidate`** — `#### N. \`<name>\` — **ambiguous candidate** (M inputs, K outputs, P pairs)`. The block carries the ambiguous-candidate id + counts only. Variants live in the sidecar `mesh-assets-<profile>-ambiguous.md`.

Before the user is prompted, `match_assets.py` has already applied two layers of auto-pruning so the remaining candidates are the genuinely-ambiguous ones:

- **Test / sandbox exclusions** drop assets whose path contains any segment in `TEST_SANDBOX_SEGMENTS` (`billg`, `sina-test`, `myenv`, `my-dp`, `placeholder`, `debug`, …) or any token starting with `hello` (`hellopython`, `hello6`, `helloincremental`, `playlistshello`). These are pre-filtered out of the candidate set entirely.
- **Production-score Pareto dominance** inside each ambiguous candidate drops pairs that are out-ranked on both sides by another pair in the same name-pair group. `prod` / `production` / `live` segments score positive; `staging` / `stg` / `dev` / `demo` / `uat` / `qa` score negative; trailing `_2`, `_3`, `-v2` on the final segment score lower. A `/prod/` input paired with a clean schema strictly dominates a `/demo/` input paired with `_STAGING`; the demo+staging pair is dropped automatically. Pairs that lead on at least one side stay.

The user still picks between any remaining variants, but the typical ambiguous candidate has already been narrowed to 2–3 genuinely-equivalent options rather than the raw 10× fan-out.

For each ambiguous candidate, the skill must:

1. **Open the sidecar** and read the input variants and output variants for that ambiguous-candidate id.
2. **Show them to the user** as numbered lists, ask which input locator is the production source and which output locator is the production target. The user can almost always tell — production paths typically sit under `/prod/`, on the canonical bucket, in a non-`_TEST` / non-`_STAGING` schema, etc.
3. **Record the pick** — the chosen input locator + output locator become the resolved pair. An ambiguous candidate with no production winner (all variants are tests / sandboxes) should be **dropped, not built**.
4. **Learn the pattern after a few picks.** Track the user's selections across ambiguous candidates and look for recurring signals:
    - Same **bucket** or **path prefix** on the input side (`output-data-product/prod/`, `<team>/prod/`, …).
    - Same **database**, **schema**, or **schema prefix** on the output side (`*_PROD`, a `CORE` schema, …).
    - Same **environment marker** (`prod` vs `demo`/`dev`/`int-test`).
    - Same **schema-stem rule** — user prefers Snowflake schemas whose name matches a parent path segment of the input (`dwn-incremental2/` → `DWN_INCREMENTAL2`).
    - Same **drop rule** — recurring schema patterns the user always drops (`*_STAGING`, numbered `_2` / `_3` siblings, `HELLO*` / `DEBUG_*` schemas).
    The skill should generalise: once 2–3 picks agree on a pattern, future ambiguous candidates where exactly one variant matches that pattern can be **auto-resolved** — quote the pattern, name the auto-pick, ask only for a one-shot confirmation rather than full re-selection. Ambiguous candidates where the pattern doesn't disambiguate (no matching variant, or several) still need a full prompt.
    Patterns the skill should always start with, before any session-specific learning kicks in:
      - `/prod/` (or `/production/` / `/live/`) in an input path beats `/demo/` / `/dev/` / `/myenv/`.
      - Snowflake schema with no `_STAGING` / `_TEST` / `_TMP` suffix beats one that has them.
      - Plain schema beats one with a trailing `_<digit>` (numbered copy).
      - Snowflake schema whose tokens overlap the input path's last meaningful segment beats one that doesn't (`DWN_INCREMENTAL2.CUSTOMER_HISTORY` beats `HELLOINCREMENTAL.CUSTOMER_HISTORY` for an input under `dwn-incremental2/`).
5. **Never let the downstream consumer (nxd-build-data-product) guess.** Pass on resolved input + output locators only.

Tell the user both main + ambiguous sidecar file paths and summarize the top candidates per domain in chat — do not paste the whole report. Walk through every ambiguous candidate with the user (or via the learned pattern) before recommending next steps. Finally, point the user to **nxd-build-data-product** to turn a resolved candidate into a real data product, and link `<app_url>/docs/#/tutorials/cli/create` for how a resolved candidate becomes a real data product on the mesh.

---

## Driver Classification Reference

Parse the `driver` field (format `nxd:<driver-name>:<version>` or `nxd-test:<driver-name>:<version>`) and extract the middle segment.

| Category | Driver patterns | Data-bearing? |
|---|---|---|
| **Storage** | `s3`, `adls`, `snowflake`, `databricks/storage`, `postgres`, `pgvector`, `kafka`, `pinecone`, `minio`, `dremio`, `duckdb`, `redshift`, `bigquery`, `gcp/bigquery` | Yes — inspect |
| **API** | `api` | Yes — external input, limited introspection |
| **Compute** | `kubernetes/compute`, `kubernetes/compute/streaming`, `databricks/compute`, `databricks/compute/streaming`, `sagemaker`, `local-python` (without `/rpc`) | No — skip |
| **RPC** | `local-python/rpc`, `kubernetes/rpc` | No — skip |
| **Governance** | `servicenow`, `databricks/access-control`, `databricks-contract`, `mock-universal`, anything unmatched | No — skip |

If a `driver` string is malformed or its `name` and `driver` fields look swapped (some profiles have this), ask the user how to classify that service rather than guessing.

## Gotchas

- **Secrets** — `attributes` carry credentials. Inspect via Python that reads the file in-process; never put a secret on a command line or in chat.
- **Read-only** — only `LIST`, `SHOW`, `DESCRIBE`, `SELECT`, `GET`, `HEAD`. Never `PUT`, `INSERT`, `CREATE`, `DROP`, `DELETE`.
- **Cost** — prefer metadata (`INFORMATION_SCHEMA`, object listings, table stats) over full scans. Sample with `LIMIT` / single-object reads to infer schema.
- **Client libraries** — recipes need driver-specific clients (`boto3`, `snowflake-connector-python`, etc.). Install on demand into a temp venv; prefer a CLI already on PATH.
- **Multiple credentials, one store** — a profile may list several services pointing at the same store with different auth (e.g. `nxd-snowflake`, `nxd-snowflake-keypair`, `nxd-snowflake-pat`). Inspect one; note the others are duplicates.
- **One service = one input** — keep the inventory aligned to how nextdata models inputs, so results map cleanly onto nxd-build-data-product.

---

## Troubleshooting inspection failures

Symptom → cause → fix for failures hit while inspecting services. A connection
failure is usually a credential, scope, or reachability problem in the infra
profile — not a bug in the analyzer. Confirm which before retrying.

| Symptom | Cause | Fix |
|---|---|---|
| Connect fails with auth error (`401`/`403`/`Access denied`/`InvalidAccessKeyId`) | The service's credentials in the infra profile are expired, revoked, or for a different account. | Verify the credentials in the profile; confirm the account/tenant matches. Treat it as a profile problem, not an analyzer bug. |
| `PERMISSION_DENIED` / wrong-catalog on a warehouse | The infra-profile catalog/schema doesn't match what the credentials can see. | Align the catalog/schema in the profile with the credential's grants. |
| Connect times out / host unreachable | The service endpoint isn't reachable from where the analyzer runs (network, VPN, allowlist). | Confirm reachability from the current host; this is environment, not data. |
| Service classified wrong / `driver` and `name` look swapped | Some profiles carry malformed or swapped driver fields. | Ask the user how to classify rather than guessing (see driver-classification table above). |
| `service not found` for a name the report referenced | The service name was invented or belongs to a different profile/mesh. | List real services for the chosen profile from the active mesh; never assume a name. |
| Inventory returns zero tables/files for a service that should have data | Wrong container/bucket/schema in the profile, or the credential's scope excludes the data. | Confirm the container/bucket/schema attribute in the profile and that the credential can list it. |

Never echo a secret value from a profile while diagnosing — inspect attributes
in-process, report only the field names. When a service is reachable but a
*deployed Data Product* built on it is failing, switch to
**nxd-debug-data-product**.
