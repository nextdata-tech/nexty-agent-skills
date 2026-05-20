---
name: nexty-mesh-analyzer
description: Inspect data-bearing services in a nextdata infra profile to discover candidate data product inputs and outputs. Reads an infra profile file, connects to selected storage services (S3, Snowflake, ADLS, Databricks, BigQuery, Postgres, Kafka, Pinecone, and more) with their connection parameters, inventories files/tables/schemas, and reports data sources that appear connected as a source-aligned data product.
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - AskUserQuestion
metadata:
  author: nextdata
  version: 0.2.0
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

This skill discovers candidates only — it does not generate data product specs. Hand the results to **nexty-bootstrap** to scaffold a data product.

---

## Scripts

The skill ships a small Python package under `scripts/`. Run the entrypoints with a Python that has the dependencies in `scripts/requirements.txt` — install into a throwaway venv:

```bash
python3 -m venv /tmp/nexty-mesh-analyzer/venv
/tmp/nexty-mesh-analyzer/venv/bin/pip install -r scripts/requirements.txt
```

**Entrypoints** (run as `python scripts/<name>.py`):

| Script | Purpose |
|---|---|
| `classify_profile.py <profile>` | Parse the profile, classify every service, list the inspectable (Storage/API) ones. |
| `inspect_service.py <profile> <service>... --out FILE` | Connect read-only, inventory each service with schema-fingerprint grouping, de-duplicate shared stores, write inventory JSON. |
| `match_assets.py <inventory.json>... [--flow SRC:DST]` | Match candidate input/output pairs, classify, and write the report + models markdown. `--flow` (repeatable) scopes matching to declared architecture flows. |

**Layout** — service-type code is isolated from generic code:

- `scripts/meshlib/` — generic core: profile parsing, schema-fingerprint grouping, the plugin registry, inspection orchestration, matching, report writing. Imports **no** service SDK.
- `scripts/drivers/` — one module per service type (`s3.py`, `snowflake.py`), each owning its SDK imports (boto3, snowflake-connector) and any per-source-type rules. An entrypoint builds a registry from these and injects it into `meshlib`.

To support another service type, add `scripts/drivers/<name>.py` exposing a `DRIVER` (see `meshlib/registry.py` and the recipes in `references/service-inspection.md`), then add it to `ALL` in `drivers/__init__.py`. The scripts read credentials from the profile in-process and never print secret values.

---

## Customer extension paths

This skill ships generically to many customer environments. Environment-specific inputs — infra profiles and user documentation — live in **customer-owned paths outside the skill**, so they survive skill updates (an update overwrites the skill directory, never these paths):

- `./.nxd/skills/nexty-mesh-analyzer/` — per-project, in the working tree
- `~/.nxd/skills/nexty-mesh-analyzer/` — per-machine / per-environment

Step 1 searches both paths. Each may hold:

- **infra profile files** — a `kind: Profile` YAML, used directly
- **user documentation** — `.md` / `.txt` describing the customer's domains, naming conventions, glossary, or which services matter
- **pointer files** — a file whose contents are filesystem path(s) or URI(s), one per line; resolve each pointer to the real infra profile or document (fetch `http(s)://` URIs, read file paths)

The skill only reads these paths — never writes to them.

---

## Flow

Run the steps in order. Inspect read-only at every step — never create, write, or delete data on a service.

**Consult the user.** The person running this skill has domain knowledge of their environment. When a decision is genuinely ambiguous — which catalog owns a table, which copy of a replicated dataset is the source of truth, which of two services is the input — ask them rather than guessing.

### Step 1: Locate inputs — infra profile and user documentation

Gather two inputs. For each, search the **customer extension paths** above plus the working tree, resolve any pointer files, and also let the user supply a path or URI directly at the prompt.

#### Step 1a: Infra profile

Search, in order:

1. The customer extension paths — `./.nxd/skills/nexty-mesh-analyzer/` and `~/.nxd/skills/nexty-mesh-analyzer/`.
2. The working tree — Glob `infra-profiles/*.yaml`, `infra-profiles/*.yml`, `*.yaml`, `*.yml`.

For each candidate: an infra profile file has `kind: Profile` and `apiVersion: infra.nextdata.com/...` near the top — confirm with Grep. A **pointer file** (contents are a path or URI) is followed to the real profile — fetch `http(s)://` URIs, read file paths.

Present every candidate found and let the user confirm which to use — or paste a path/URI of their own. Read the chosen file.

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

### Step 3: Credential handling

The infra profile file contains **live credentials in plaintext**. Before inspecting:

- Tell the user the file holds real secrets and that inspection will connect to live services.
- Never echo a secret value into the chat or into a displayed command line.
- Inspect via short Python scripts that read the profile file **directly** and pass credentials in-process — do not interpolate secrets into shell command arguments (they would appear in the displayed command and tool output).
- Write inspection scripts under a temp path (e.g. `/tmp/nexty-mesh-analyzer/`). Delete them when done.

### Step 4: Inspect each selected service

Run `scripts/inspect_service.py <profile> <service>... --out <file>` — it connects read-only, inventories each service with schema-fingerprint grouping, de-duplicates shared stores, and writes the inventory JSON. Driver plugins for `s3` and `snowflake` ship under `scripts/drivers/`; for any other driver, follow the matching per-service recipe in `references/services/<type>.md` (indexed by `references/service-inspection.md`) and add a new `scripts/drivers/<name>.py` module.

Build an **asset inventory** for the service. For every data asset record:

- **Locator** — full path/URI or fully-qualified table name.
- **Kind** — `file`, `directory`, `table`, `topic`, or `index`.
- **Format** — csv, parquet, json, iceberg, delta, etc.
- **Schema** — column/field names with types (infer from a file sample or `DESCRIBE`).
- **Partitioning** — partition keys or `key=value` / date-style path segments, if any.
- **Size** — object/row count and total bytes where cheap to obtain.
- **Last modified** — most recent write timestamp.

**Group file-based storage by schema fingerprint, not by directory path.** Path-based grouping fails both ways: a bucket laid out as `<data-product>/<port>/...` collapses a whole product into one asset, while a raw partitioned export explodes one dataset into one fragment per partition. Instead — infer each file's schema, then group files that share an identical schema and format into one logical asset. Path segments that *vary within a group* are **partition keys** (`key=value`, date segments, numeric ids) — record them as partitioning, do not split on them. Per the nextdata convention, treat **one infra service as one input** and **each unique schema as its own input model**.

**Delta / Iceberg tables are one asset.** A Delta or Iceberg table on file storage is a single logical table, not the pile of `_delta_log/`, `metadata/`, and UUID-named data files it is made of. `inspect_service.py` detects a table root and emits one `table` asset, taking its schema from the table metadata — that metadata is the authority and it points at the underlying parquet/avro. If a table is also registered in a catalog service (Unity Catalog, Snowflake) and it is unclear which catalog owns it, ask the user.

**De-duplicate stores.** If two selected services point at the same physical store (identical `bucket`, or identical `account`+`catalog`+`schema`), inspect it once and mark the others as duplicates — don't re-scan.

The inventory can run to thousands of assets. Write it to a file under the temp dir and work from a summary — never dump raw inventory JSON into the chat.

If a connection fails (bad credentials, network, missing client library), report it and continue with the other services — don't abort the whole run.

### Step 5: Match candidate inputs and outputs

**First, confirm flow directionality with the user.** Using the data-architecture documentation (Step 1b) and the actual databases, buckets, and tables discovered in Step 4, derive the candidate service→service flows. Present each to the user and have them **confirm or correct its direction** — which service is the input (source) and which is the output. Do not infer direction from naming: an `_az` / `_azure` / region / environment suffix does **not** tell you which side is upstream — only the architecture and the user do. Pass the confirmed flows as `--flow <input-service>:<output-service>` to `match_assets.py`.

Run `scripts/match_assets.py <inventory.json>` over the inventory from Step 4. It applies the heuristics in `references/connection-matching.md` to find connected pairs:

- Drop assets and pairs that the exclusion rules reject — Snowflake clone tables, hello-world test data, same-database plural twins, bucket/account-root assets (see `references/connection-matching.md`).
- Set aside **replicated datasets** — a dataset copied verbatim across 3+ stores. These are not an N×N grid of products; they go to a separate report section (see below).
- Pair the rest by schema similarity, related naming (`input`/`output`, `raw`/`curated`, `bronze`/`silver`/`gold`), matching asset names, partitioning carried through, and output-modified-after-input.
- Infer direction (which asset is the input, which is the output).
- Classify each candidate product as **source-aligned** (near-identical model, minimal transform; canonically file storage → database) or **transformed** (aggregated/joined/reshaped). A same-service pair is at most low-confidence source-aligned.
- Score confidence; report **high/medium** confidence pairs as candidates and list **low** confidence ones separately as "possible".

**Replicated datasets — ask the user.** The report's "Replicated Datasets" section lists each dataset that appears identically across 3+ stores. For each, prompt the user: *"`<dataset>` is replicated across [list of locations]. Which is the source of truth (the input)?"* The user has the domain knowledge to answer. Once they pick the canonical source, the source → each other location is a source-aligned candidate; record those.

**Large multi-database accounts — scope with the architecture.** When the inventory spans many services or a database with thousands of tables, pairwise matching produces a huge, noisy candidate set — many tables coincidentally share a schema. Two databases in one account are **not** auto-collapsed into one system and **not** assumed unrelated. Use the **data-architecture documentation from Step 1b** to know which service→service flows are real, then pass each as `--flow <input-service>:<output-service>` to `match_assets.py` (repeatable) — only declared flows are scored. This tames the candidate count and drops services that are not part of any flow (e.g. a platform-metadata database). If no architecture documentation exists, prompt the user — which databases feed which — before matching; do not dump an unscoped candidate list.

`match_assets.py` classifies domains and suggests names heuristically. If user documentation from Step 1b defines the customer's domains, glossary, or naming conventions, apply it: correct the heuristic domains and suggested names to match — customer documentation overrides the generic heuristic.

### Step 6: Report

`match_assets.py` writes **two** markdown files — pass `--out mesh-assets-<profile>.md`:

- **`mesh-assets-<profile>.md`** — candidate data products, **grouped by domain**. Each candidate carries: suggested data product name, domain, infra profile name, and — for both its input and its output data source — the location, the service name, and the infra-profile service URL; plus the source-aligned/transformed classification, confidence, and evidence. Also lists unmatched assets, duplicate services, and failed services.
- **`mesh-assets-<profile>-models.md`** — the input and output model schemas (columns and types) of each candidate, kept in a separate file for readability.

These two files are the deliverable a downstream data-product-authoring skill consumes.

**Domains.** Data products live in domain groups. `match_assets.py` classifies each candidate's domain heuristically from its naming; anything it cannot classify is filed under `other`. The infra profile file does not record domains authoritatively — prefer the customer's domains from the Step 1b user documentation when available, then review the assigned domains with the user and correct any that are wrong.

**Service URLs.** A service URL has the form `infra-profile/<profile>#/services/<service>`. Pass `--api-url <mesh-api-url>` to `inspect_service.py` to make it absolute; without it the URL is relative and the consumer prepends the base. Ask the user for the mesh API URL if they have one.

For time-partitioned inputs (date or `dt=`-style segments), the report records the partition keys — the partition granularity implies the transform's refresh cadence.

Tell the user both file paths and summarize the top candidates per domain in chat — do not paste the whole report. Finally, point the user to **nexty-bootstrap** to turn a candidate into a real data product.

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
- **One service = one input** — keep the inventory aligned to how nextdata models inputs, so results map cleanly onto nexty-bootstrap.
