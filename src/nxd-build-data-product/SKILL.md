---
name: nxd-build-data-product
description: Guide for creating, scaffolding, refining, and validating a Nextdata OS Python-based data product, including the interactive bootstrap wizard for a brand-new product. Two discovery modes — an interactive interview that walks through inputs, semantic models, transforms, outputs, glossary links, and contracts, or spec-from-document (e.g. a candidate in a `mesh-assets-PROFILE.md` report produced by `nxd-analyze-mesh`). Use when the user mentions building, bootstrapping, scaffolding, or iterating on an `nxd` data product, references files like `spec.py`, `models.py`, or `transform.py`, or asks about Nextdata OS drivers, semantic models, or transformations. Do not use for generic Python data pipelines unrelated to Nextdata OS.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - MultiEdit
  - Glob
  - Grep
  - AskUserQuestion
metadata:
  author: nextdata
  version: 0.38.4
---

# Nextdata OS data product builder

## Overview
Support the design, planning, implementation, and refinement of a Nextdata OS Python-based data product through structured collaboration with the user. Rely on verified references and confirm decisions at every step.

This Skill is intended for technically proficient users who are familiar with technical terms and concepts. Minimise assumptions and seek clarity from the user throughout the workflow.

---

## Prerequisites
Before engaging with the user, set up the environment. Do **not** proceed until this is complete.

- **NXD CLI:** Ensure the NXD CLI is installed and the correct mesh is selected, this should be set up and verified by the "nxd-setup-cli" Skill. *Confirm the correct mesh has been selected before continuing.*
- **Active mesh + its hosts (elicit-or-derive, do not hardcode):** every service URL, doc link, and `nxd ... --config` flag in this skill depends on which mesh is active. `nxd-setup-cli` owns mesh selection and writes the per-mesh config to `<session_config>` (`/tmp/...` on POSIX/WSL, `$env:TEMP\...` on Windows PowerShell). Confirm the active mesh **name** with the user (or read it from the nxd registry at `~/.nxd/meshes.json` — the selected entry), and from that same mesh entry take its `app_url`/`api_url` host. These are the host you substitute into `https://<app_url>/infra-profile/<profile>#/services/<service>` URLs and into the docs base below. Never paste a demo host (`example.com`, `nextopia.dev`, `nextdata.com`) as if it were canonical — those only appear as clearly-marked illustrative placeholders.
- **Runtime:** Python **3.10** with **`uv`** as the dependency manager.
    - *There is no need to check for a given Python version since `uv` will manage this for us.*
- **Dependencies:** Install the `nxd-data-product` Python package from the mesh's package registry index (commonly `https://registry.trynxd.com/index/`; if your mesh config specifies a different index, use that):

```
uv init --bare --python 3.10
uv venv --python 3.10
uv add nxd-data-product --index nxd=https://registry.trynxd.com/index/
```

*Critical: Do not rely on internal or assumed knowledge regarding Nextdata OS or its Python packages. Always verify usage against the locally installed version of the `nxd` Python package.*

### Platform docs (per-mesh)
Docs are served **per-mesh** from the active mesh's app host — there is no single global docs URL. Resolve the base from mesh config (the `app_url` of the selected mesh in `~/.nxd/meshes.json`, exactly as `nxd-setup-cli` records it), then build links as `<app_url>/docs/#/<path>` (docsify hash routing — keep the `#/`, no `.md` extension). The doc paths most relevant to *building* a data product:

| Topic | Path (append to `<app_url>/docs/#/`) |
|---|---|
| CLI setup / mesh + auth | `tutorials/cli/setup` |
| Create a data product (CLI) | `tutorials/cli/create` |
| Inputs | `tutorials/guides/04-inputs` |
| Outputs | `tutorials/guides/02-outputs` |

Hand these out **inline and contextually** at the matching step below (full path table in [reference/platform-docs.md](reference/platform-docs.md)). If a deep link 404s, open the docs home `<app_url>/docs/#/` or the in-app Learn tab rather than guessing paths. Prefer **showing** live with `nxd` over linking where you can.

---

## Data product creation workflow
Copy this checklist into your response and tick items off as you complete them:

```
Data product build progress:
- [ ] 0. Prerequisites verified (NXD CLI, mesh selected, uv env, nxd-data-product installed)
- [ ] 1. Discovery complete (interview answered OR spec-from-document extracted; infra profile located; references consulted)
- [ ] 2. Plan approved by user
- [ ] 3. Implementation complete (files written to a real project directory OR delivered as downloadable artifacts)
- [ ] 4. Validation complete (`nxd validate` result recorded as PASS, FAIL, or NOT RUN with reason)
- [ ] 5. README, requirements checklist, and handover summary make location/status/next steps explicit
```

### Project Location and Delivery Mode
Before writing code, decide and state the `data_product_directory`. Prefer a
real local directory with an absolute path. If the execution environment cannot
write to the user's filesystem and only supports chat artifacts/downloads, say
that explicitly before generating files and record:

```
Project location: Claude Desktop conversation artifacts only
Local filesystem path: Not created until the user clicks Download all
Recommended local path after download: <absolute-path>
```

Never claim "built in `<directory>`" unless you have created or inspected that
directory in the current environment. If files are delivered as downloadable
artifacts, call them "downloadable artifacts", not a local project directory.

For a longer or multi-session build, you may keep an optional lightweight ledger
(`state.json` + `open-todos.md`) under `.context/dp-build/<timestamp>/` so the
build can be paused and resumed without losing context. On startup, check whether
`.context/dp-build/` already holds a prior run and offer to resume it. See
[reference/state-and-resume.md](reference/state-and-resume.md) for the resume
protocol and ledger format.

### 1. Discovery and Requirements Gathering
Start by deeply understanding the user's intent, objectives, and requirements for the proposed data product.

#### Research
Consult the following references for concepts, APIs, and best practices:

* Real-world examples of implemented data products — bundled as a submodule at [reference/nextdata-public-examples/](reference/nextdata-public-examples/); see [reference/examples-guide.md](reference/examples-guide.md) for selection and drafting rules.
    * Ignore the single-import rule present within examples, it does not apply to newly built data products.
* Information regarding best practices, preferred approaches and more: [reference/best_practices.md](reference/best_practices.md)
* Overview of Nextdata OS concepts: [reference/concepts.md](reference/concepts.md)
* Data product structure and build process: [reference/build.md](reference/build.md)
* In-depth details of the critical `data_product()` function: [reference/data_product_spec.md](reference/data_product_spec.md)
* In-depth details of `semantic_model()`: [reference/semantic_model_spec.md](reference/semantic_model_spec.md)
* Storage config helpers, source-URL patterns, and transform context types per driver: [reference/storage-configs.md](reference/storage-configs.md)
* Concrete file templates (`spec.py`, `transform.py`, models, requirements) and the driver-classification table: [reference/file-templates.md](reference/file-templates.md)
* Running `transform()` locally: [reference/local_transform.md](reference/local_transform.md)
* Examples of drivers (services) used within transformations: [reference/driver_examples.md](reference/driver_examples.md)
* Authoring-time pitfalls (triggers, requirements, naming, types): [reference/common-pitfalls.md](reference/common-pitfalls.md)
* Debugging a deployed data product (symptom → root cause → fix): [reference/troubleshooting.md](reference/troubleshooting.md)
* Classifying a candidate into a data product type, with evidence discipline: [reference/product-taxonomy.md](reference/product-taxonomy.md)

#### Discovery Source — interview or spec-from-document
Decide once, up front, how the data product's requirements will be sourced. Ask the user which mode applies:

* **Interactive interview** (default) — work through the questions in **Interview** below.
* **Spec-from-document** — the user points at one or more documents that already describe the data product. The canonical case is a candidate `#N` in a `mesh-assets-<profile>.md` report produced by the **`nxd-analyze-mesh`** skill, paired with its companion `mesh-assets-<profile>-models.md` for input/output schemas. Phrases like *"build the data product described by #41 in mesh-assets-daff.md"* trigger this branch.

If spec-from-document is chosen, follow **Spec-from-Document** below in place of Interview. Either branch must end with the same outputs: the candidate's purpose, inputs/outputs (with locations, services, formats), drivers, and any transformation notes. Confirm the extracted answers with the user before moving on to step 2.

#### Spec-from-Document
For each document path the user supplies (file path or `http(s)://` URL), read it and extract the requirements that would otherwise come from Interview. Where the document is missing an answer, fall back to asking the user just that question.

**Mesh-assets report — the primary supported format.** A `mesh-assets-<profile>.md` lists candidates grouped by domain, each numbered (`#### 41. \`<name>\``). Each candidate carries:

- *Suggested data product name* — use as the data product name unless the user overrides.
- *Domain*, *Infra profile*.
- *Classification* — `source-aligned` or `transformed` (with confidence). Source-aligned + file→database typically means lift-and-shift with minimal logic; transformed means real reshaping.
- *Input data source* — `location`, `service`, `service URL`. The service name maps to a service in the infra profile (see Infra Profile Lookup below).
- *Output data source* — same three fields.
- *Evidence* — schema jaccard, shared tokens, lineage signals. Read this — high jaccard + source-aligned says the transform is essentially a passthrough; a long shared-token list hints at columns to forward verbatim.

Pair the report with its companion `mesh-assets-<profile>-models.md`. That file has one section per candidate (matched by number) with full input and output schemas as `| column | type |` tables. Use these to seed `models.py` semantic models.

If the user refers to a candidate by number (`#41`) or by name (`top-playlists`), locate that block in both files and read it. If the user gives only the report file with no candidate selector, present the candidates grouped by domain and ask which one to build.

Other document shapes — plain markdown or text describing a data product — are supported best-effort: read the document, extract whatever maps onto the Interview questions, then ask the user to fill any gaps.

**Build a doc-claim checklist before any code.** Before writing `spec.py` / `models.py` / `transform.py`, enumerate every concrete claim from the input doc as a flat list: data product name, domain, infra profile, mesh URL, each input port (service + driver + filters + expectations), **each output port** (service + driver + schema + table + model + format), transform constraints (chunk sizes, embedding models, library choices), schedule, model count and shape, validation expectations. Treat each paragraph of a section like *Output* as a potential standalone claim — sections often carry N facts, not one. After scaffolding, walk the checklist and mark which file/line implements each claim. Anything unmapped = revisit before reporting done. When a claim conflicts with a similar reference example, **the doc wins**.

#### Infra Profile Lookup
Both discovery branches need to know the infra profile file to wire services into `spec.py`. Locate it the same way `nxd-analyze-mesh` does, then confirm with the user.

The infra profile must be **derived from the active mesh or elicited from the user — never hardcoded** (do not assume `ecommerce`, `ecommerce-demo`, or any demo name). Search, in order:

1. Customer extension paths — `./.nxd/skills/nxd-build-data-product/` and `~/.nxd/skills/nxd-build-data-product/`.
2. Working tree — `infra-profiles/*.yaml`, `infra-profiles/*.yml`, `*.yaml`, `*.yml`.
3. The active mesh itself — when no local YAML resolves the profile, enumerate what the mesh actually offers with `nxd ls infra-profiles --config=<session_config>` and let the user choose from the returned names. To list services for a chosen profile, use `nxd --config=<session_config> rest -u /api/v1/infraprofiles/<profile-name>/services` (spelling is `infraprofiles`, no hyphen). The profile name selected here is the value you place in `infra_profile="..."` and in service URLs.

For each candidate file, confirm with `Grep` that it has `kind: Profile` and `apiVersion: infra.nextdata.com/...` near the top. Resolve **pointer files** — a file whose contents are filesystem path(s) or URI(s), one per line — by following each pointer (read file paths, fetch `http(s)://` URIs).

Present every match and let the user pick one, or paste a path / URI directly. When the discovery source is a mesh-assets report, prefer the profile whose `metadata.name` matches the candidate's *Infra profile* field.

**Mesh URL = active nxd config, not the doc default.** Service URLs in `spec.py` (`.source(...)`, `storage(...)`, `.compute(...)`) must point at the user's **active mesh** — the un-commented `url:` line at the top of `~/.nxd/config.yaml`. If the input doc / mesh-assets report names a different mesh host, **flag the mismatch and ask the user which mesh to target** before generating files; don't silently use either. Reference examples may carry whatever mesh their author used — treat the host as a template, not a value to copy verbatim. Once chosen, confirm the named services (`<input-service>`, output service, compute) actually exist in the chosen mesh's infra profile by grepping the profile YAML; missing services will fail `nxd validate` / `nxd launch` later.

**Credentials.** The chosen profile holds live secrets in plaintext. Treat it the same way `nxd-analyze-mesh` does:

- Never echo a secret value to chat or display it on a command line.
- When the builder needs service attributes (URLs, account names, bucket names) to populate `spec.py`, read them out of the profile and put them in `spec.py` — but pull credential values (passwords, access keys, tokens, client secrets, PEM blocks) into `.env` placeholders instead, with a `TODO` marker.
- The local transform script reads credentials from the environment, never from `spec.py`.

#### Interview
Use this branch when discovery source is **interactive interview** — the
guided bootstrap path for a brand-new product (replaces the former
`nexty-bootstrap` wizard). Ask conversationally, one topic at a time, and
confirm each answer before advancing. The numbered prompts below are concrete
starting questions; adapt wording to the user's context.

**a. Where does the data come from?** "Where is the data for this product
coming from?" Steer to exactly one of:
* **Existing data** — a file or a remote service (S3, Snowflake, ADLS,
  Databricks). For a local file, read it and infer the schema (columns, types,
  sample values). For a remote service, help the user pull a small sample or
  `DESCRIBE`/metadata, then infer the schema. Confirm the inferred input model.
* **Existing source code** — read the codebase to learn what it reads
  (inputs), what it transforms, and what it produces (outputs); pre-populate
  models from it.
* **Other data products** — `nxd ls data-products`; the user picks upstream
  products and each becomes a `data_product_input().source(...)` pointing at
  that product's output port. Reuse the upstream's published semantic models
  as inputs where available.

**b. Domain, infra profile, and basics.** Elicit-or-derive — none of these are
hardcoded defaults. **Domain:** confirm the domain the user may launch in
(elicit it, or derive launchable domains from the active mesh; the heavier
CLI/REST role/domain walk-through lives in `nxd-analyze-mesh`). **Infra
profile:** locate or enumerate it via **Infra Profile Lookup** above (local
YAML, else `nxd ls infra-profiles` against the active mesh) and confirm with
the user. From the profile, identify the available services and classify each
as compute / storage / rpc / governance (driver-classification table in
[reference/file-templates.md](reference/file-templates.md)); when only the
mesh (no local YAML) lists services, take service names from there. *Doc:
the end-to-end CLI scaffolding flow is at `<app_url>/docs/#/tutorials/cli/create`.*
Then pin the
basics: **name** (kebab-case, suggested from the source), **description**,
**version** (default `0.1.0-dev`), **source repo URL** (detect via
`git remote get-url origin` when in a repo). Pin **transform compute** (auto-
select if only one) and **output storage destination(s)** — these are
referenced, not re-asked, later.

**c. Inputs and semantic models.** For each input: a kebab-case name, the
input type (`source_aligned_input()` for raw/external storage, or
`data_product_input()` for an upstream DP), the source URL selected from the
profile's storage services, and a `semantic_model()` (snake_case name,
description, typed schema). Present any models inferred in (a) for the user to
adjust. *Docs: `<app_url>/docs/#/tutorials/guides/04-inputs` (source vs DP
inputs); for depending on another team's DP,
`<app_url>/docs/#/tutorials/guides/consumer-tutorial`; semantic-model rules at
`<app_url>/docs/#/tutorials/guides/01-semantic-model`.*

**d. Outputs and semantic models.** "What data does this product produce?" —
frame it concretely using the locked input format and output storage (e.g.
"given Parquet on ADLS in and Snowflake out, what models should this expose?").
Collect each output model the same way. Then:
* **Glossary matching (always do this):** fetch available glossary terms and
  propose matches against output field names/descriptions; record confirmed
  ones via `.link("field", Predicate.GlossaryTerm, "<glossary-full-name>#/terms/<id>")`.
  If none match, say so explicitly and move on.
* **Upstream links (source-code or DP-input products only):** where an output
  field traces to an input field, record
  `.link("output_field", Predicate.SameAs, "<input-model>#/schema/<input-field>")`.
  Skip for pure source-aligned products — outputs mirror inputs 1:1.

*Docs: output ports at `<app_url>/docs/#/tutorials/guides/02-outputs`.*

**e. Transform logic.** "Describe what the transformation does — how do inputs
become outputs?" Use the compute service already chosen. The transform reads
each input via its context type, writes each output port, and carries clearly
labelled TODO markers for the real logic.

**f. Output ports.** Map output models to ports. Auto-name each port from its
storage driver (e.g. `nxd_snowflake`, `iceberg_on_s3`); with one storage
destination all models share a port, with several ask which models route where.
*For an RPC/MCP output port, see `<app_url>/docs/#/tutorials/guides/07-mcp`.*

**g. Quality, access, trigger.** Optional but offer them:
* **Data quality** — choose one or more promise types for outputs, or expectations for inputs:
  - **Great Expectations**: Python file in `contracts/` with `configure() -> list`; wire with
    `quality(gx, "contracts/<file>.py").name(...).model(model)` on the port.
    Requires `nxd_data_product[gx]` in requirements.txt.
  - **Soda**: YAML file in `contracts/` with `checks for TABLE_NAME:`; wire with
    `quality(soda, "contracts/<file>.yml").name(...).model(model)` on the port.
    Requires `nxd_data_product[soda]` in requirements.txt.
  - **Custom**: Python file with `verify(snowflake, ctx, models, triggered_by) -> VerifyResult`;
    wire with `custom("name").model(model).verify(code(fn))` at the output level.
  Omit `.model(model)` on GE/Soda to run against all canonical output models.
  See [reference/promises-contracts.md](reference/promises-contracts.md) for templates.
* **Access** — **elicit** the owner / data-steward / consumer email addresses
  from the user; these are environment-specific identities, not defaults. Do
  not copy any `@nextdata.com` / `@example.com` address from reference
  examples — those are placeholders only.
* **Trigger** — should it run when an input updates (`updated("my-input")`,
  where the argument is the `.input()` name, **not** the upstream DP name) or
  on a schedule (`scheduled("0 */8 * * *")`)? If a time-partitioned input
  implies a cadence, seed that cron. Both is fine via `any_of(...)`.
  *Scheduling: `<app_url>/docs/#/tutorials/guides/06-scheduling`.*

Also cover the underlying technical questions for any path:

1. Intended purpose and outcome of this data product.
2. Expected inputs and outputs, and their formats.
3. Drivers (services) needed, whether Nextdata OS supports them, and the
   service names + infra profile they belong to.
4. Transformation approach — preferred patterns or tooling, plus any docs or
   third-party material (documentation sites, OpenAPI specs) to aid it.

#### Directed Research
Based on the user's answers, perform additional research as needed, particularly if any of the following is true:

* Data will be sourced or processed via an "off-mesh" service such as an API or website.
    * Request supporting documentation, such as a reference website or OpenAPI specification.
    * Identify suitable (up-to-date, well-regarded) Python libraries that could be used.
    * Strongly suggest that the user provides example code snippets for service integration, such as a `requests.get()` call.
    * If the expected data structure is not clear from documentation or code snippets, confirm it with the user.
* Data will be "vectorised" — i.e. stored within a vector store such as pgvector.
    * Determine the preferred embedding model.
    * Decide on a chunking strategy if required.
    * Confirm any library preferences with the user.

Where the questions are very specific, guide the user by offering recommendations and examples for them to confirm.

### 2. Planning and Design
Use all gathered information to create a clear, actionable plan for the data product's implementation. Ideally the plan should be simple while still achieving the user's end goals.

Highlight critical decisions, uncertainties, and options for explicit user confirmation, including:

* The input and output drivers (services) that will be used and their configuration.
* A high-level overview of the transformation pipeline, drawing particular attention to areas where you are least certain.

**Generate-it-right rules — bake these into the plan:**

* **Source-aligned is the default.** Unless the user is genuinely reshaping
  data, model the product as source-aligned (output mirrors input). Only treat
  it as transformed when there is real logic — reshaping, joins, aggregation,
  enrichment.
* **One input per service.** Keep the input inventory aligned to how Nextdata
  models inputs — one `.input(...)` per source service, not per file.
* **One semantic model per unique schema.** Don't duplicate a model that
  already describes a schema; reuse it across inputs/outputs that share it.
* **Contracts: expectations on inputs, promises on outputs.** Attach
  `.expectation(...)` at the input. For outputs: GE and Soda promises attach at
  the **port** (`storage(...).promise(quality(...))`); custom promises attach at
  the **output** (`data_product_output().promise(custom(...).verify(code(fn)))`).
  See [reference/promises-contracts.md](reference/promises-contracts.md).
* **Time-partitioned input → cron in `.when()`.** If an input is partitioned
  by time, the partition granularity implies the refresh cadence (daily
  partitions → a daily `scheduled(...)`); otherwise prefer
  `updated("<input-name>")` triggers.

Share the plan for explicit user approval before moving forward.

---

### 3. Implementation
Begin implementation once the plan is finalised. To pick the closest public
example to adapt — by infrastructure and capability — and for on-demand cloning
guidance and drafting rules, see [reference/examples-guide.md](reference/examples-guide.md).

When no example fits cleanly, scaffold from the concrete templates in
[reference/file-templates.md](reference/file-templates.md) — `spec.py`,
`transform.py` (incl. an S3-CSV → Snowflake external-table pattern), the
`inputs/`/`outputs/` model files, `requirements.txt` (with per-driver
dependencies), the generated-file layout, and the driver-classification table.
For storage `.config(...)` helpers and per-driver transform context types, see
[reference/storage-configs.md](reference/storage-configs.md).

Insert "TODO" markers with clear instructions wherever any of the following are true:

* The user has not provided satisfactory information even after prompting.
* There are implementation details that would greatly benefit from manual user intervention.

Always create `README.md` and `REQUIREMENTS_CHECKLIST.md` alongside the code.
The README must start with a short status block before any architecture detail:

```
# <data-product-name>

## Build Status
| Item | Status | Evidence / next action |
|---|---|---|
| Project files | CREATED / ARTIFACTS ONLY | <directory path or download instruction> |
| Local smoke test | PASS / FAIL / NOT RUN | <exact command and result> |
| nxd validate | PASS / FAIL / NOT RUN | <exact command, output summary, or blocker> |
| nxd launch | NOT RUN / PASS / FAIL | <must say if launch was intentionally skipped> |
| Runtime resources | CREATED / NOT CREATED / UNKNOWN | tables, buckets, vector indexes, schedules |
```

Then include: layout, how to run local tests, how to run `nxd validate`, how to
launch only after approval, and a direct pointer to `REQUIREMENTS_CHECKLIST.md`.
The checklist must map every open TODO to the file to edit, the decision needed,
and the command to re-run after fixing it.

#### `spec.py`
* Ensure the infrastructure profile is included (by name — `infra_profile="<name>"`).
* Configure each driver (service) with the appropriate URLs and settings, whether it is an input (`source()`) or an output (`storage()` etc.).
* Service URLs are full and inlined: `https://<app_url>/infra-profile/<profile>#/services/<service>` — used as-is in `.source(...)`, `storage(...)`, `.compute(...)`. Do not abstract behind a helper. `<app_url>` is the active mesh's app host **resolved from mesh config** (see Prerequisites), `<profile>` is the infra profile chosen in discovery, and `<service>` is a real service name from that profile — none of these are hardcoded demo hosts/names.
* Read the chosen infra profile YAML to discover the correct service names; the compute service name in particular varies between profiles (`k8s-compute`, `k8s-executor`, a Databricks compute, etc.).
* Project-local `nxd_spec.py` and `nxd_models.py` shim modules are required — the wildcard imports in `spec.py` / `models.py` resolve through these. See `reference/best_practices.md` for the template.
* Do not run `python spec.py` directly. For a local pre-validate import/build check, use the package-loader command in the Validation section; it injects the expected filesystem root the DSL needs.

#### `models.py`
* Avoid complex types in semantic models where possible, due to compatibility limitations.

#### `transform.py`
* Use Nextdata Contexts via explicit imports (e.g. `from nxd.data_product.context import AzureDataLakeStorage`) to pass configuration, credentials, and models for each input or output driver. Prefer explicit imports over wildcard imports within the transformation file(s).
* Keep heavy runtime dependencies (Spark, torch, sentence-transformers, langchain embedding/vector integrations, browser clients) out of top-level imports. `nxd validate` imports `spec.py`, which imports `transform.py`; heavy top-level imports can make validation fail before the transform runs. Import heavy libraries inside `transform()` or helper functions.
* Parameter names in the `transform(...)` signature must match the input and output-port names declared in `spec.py`. For example, `.input("comp_public", source_aligned_input()...)` binds to `def transform(comp_public: API, ...)`, and `.port("adls", storage(...))` binds to `adls: AzureDataLakeStorage`. Hyphens in spec names are normalised to underscores in the Python signature (e.g. `"s3-source"` → `s3_source`).

#### `nxd` Library
The `nxd` library should already be installed in the virtual environment by the prerequisites step. Always refer to the locally installed version for implementation details rather than relying on prior knowledge.

#### Transformation Validation
Although the `transform(...)` function is designed to run within the Nextdata OS platform, it is worth creating an additional script that can execute it locally — this is very useful for testing. Any Python libraries required only for running the transformation locally should be added as development dependencies (e.g. `uv add --dev <package>`) so they are recorded in `pyproject.toml` without being treated as runtime dependencies of the data product, *including `python-dotenv` if used*.

**Exercise the full pipeline, not just the I/O boundary.** A local test that only confirms "did the input fetch succeed" passes happily while the transform breaks at parse time — real-world APIs often return fields in shapes the naive code path doesn't anticipate (nested document trees instead of strings, optional containers, vendor-specific encodings). The local test must walk every internal stage the transform walks: fetch → parse / extract → chunk / aggregate / shape → (write is fine to stub if the sink is hard to reach locally). Run it against real upstream data when credentials are available; assert that each stage produces non-empty output across the full sample, not just the first record. Stage failures should report with the stage name (`FAIL[parse]: …`) so the breakpoint is obvious.

#### Packaging for `nxd launch`
The platform's init container installs the data product as a Python package via `pip`, which uses `setuptools` for discovery. A flat directory with multiple top-level `.py` files (`spec.py`, `models.py`, `transform.py`, plus the `nxd_spec` / `nxd_models` shims) breaks auto-discovery and the launch fails at `Installing dependencies` with `Multiple top-level modules discovered in a flat-layout`. Two things prevent this:

* **Declare `py-modules` explicitly in `pyproject.toml`** (see `reference/best_practices.md` for the snippet). List every `.py` module that should ship — typically `spec`, `models`, `nxd_spec`, `nxd_models`, `transform`, plus contract files if any.
* **Ship a `.nxdignore`** that excludes everything local-only from the deployment bundle: `.env*`, `local_transform.py` (and any other local runner / smoke-test script), `.venv/`, `__pycache__/`, build artifacts, IDE / VCS noise. Local-execution files have credentials wired in or use development-only dependencies the platform shouldn't see.

#### Generated-Code Preflight
Before handing files to the user, run the checklist in
[reference/generated-code-preflight.md](reference/generated-code-preflight.md).
Fix what you can, and record every unresolved launch or validation risk in both
`README.md` and `REQUIREMENTS_CHECKLIST.md`.

---

### 4. Validation
Once implementation is complete, validate the data product before handover. Track progress with the following checklist:

```
Validation Progress:
- [ ] Generated-code preflight completed; unresolved risks recorded in README/checklist
- [ ] Local transform script in place; imports resolve and function signatures match declared context types
- [ ] All "TODO" markers inserted and clearly labelled
- [ ] Local smoke test run, or recorded as NOT RUN with a concrete blocker
- [ ] Offline spec-build check run with `data_product_spec_from_file_at_path(...)`
- [ ] `nxd validate --config=<session_config> <data_product_directory> --debug` passes
```

Run the offline spec-build check before mesh validation:

```
python - <<'PY'
from pathlib import Path
from nxd.spec.fs.package_loader import data_product_spec_from_file_at_path
data_product_spec_from_file_at_path(Path("spec.py"), Path("."))
print("offline spec-build: PASS")
PY
```

Then validate against the chosen target mesh. `nxd validate` imports the bundle,
connects to the `--config` mesh, resolves the infra profile/services, and may
fail on missing services or auth. It does not execute the transform body. Do
not leave the user to interpret raw output: run `nxd --config=<session_config>
whoami`, run validate, capture `$?` or `$LASTEXITCODE`, and summarize `PASS`,
`FAIL`, or `NOT RUN`. If `whoami` prints `Not logged in`, treat validation as
`NOT RUN` even if the command exits `0`. If a cross-mesh probe fails but target
validation later exits `0`, remove stale cross-mesh blockers from the README.

If `nxd validate` reports errors, read the output carefully, fix the issue in `spec.py`, `models.py`, or `transform.py`, and re-run until the command exits cleanly. Do not mark item 4 complete on the top-level checklist until validation passes.

If `nxd validate` cannot be run, do not leave the user to infer that from prose.
Record it as `NOT RUN` in the README status block, the final response, and the
handover checklist, with the exact blocker and the exact command the user should
run next.

End-to-end runtime validation is performed by the user in the Finalisation step.

**Watch for semantic-model removal across versions at launch time.** The platform protects downstream consumers from breaking changes: if a previously launched version of the same data product declared a semantic model that the new launch no longer declares, `nxd launch` aborts with HTTP `409` and a message like `The following model(s) are no longer available: [<model_name>]`. This commonly happens when the model is renamed during scaffolding (e.g. an unintended pluralisation / casing change) — the rename looks local but the server sees deletion. Two resolutions:

* **Rename the model to match the prior name** in `models.py`, `spec.py`, `nxd_spec.py`'s `__all__`, the `target_table(...)` model argument, and any model-name string constants in `transform.py`. Re-run launch.
* **Bump `manifest.version` and launch with `--versioned`** so the previous version coexists.

If you're not sure which model name the deployed version uses, `nxd describe data-product <name>` (or the DP REST `/api/v1/models` endpoint) lists them.

---

### 5. Finalisation and Handover
Once implementation is complete, deliver a handover summary to the user. The
first lines must answer: where the files are, whether they are local files or
downloadable artifacts, what has passed, what has not run, and whether anything
exists in the target mesh yet.

Include the following checklist for them to work through:

```
Finalisation (user to complete):
- [ ] If files were delivered as artifacts, click Download all and move/extract them into the named local directory
- [ ] Review all "TODO" markers; resolve or explicitly defer each
- [ ] Populate `.env` (or equivalent) with credentials and configuration for local execution
- [ ] Run the local smoke test command shown in README.md
- [ ] Run validation: `nxd validate --config=<session_config> <data_product_directory> --debug`
- [ ] Run the local transform script and confirm it completes end-to-end
- [ ] Launch the data product on the mesh: `nxd launch --dir <data_product_directory> --config=<session_config>`
- [ ] Verify the first platform run: transform completes, outputs land at configured ports, promises/expectations pass
```

If the launched data product fails or behaves unexpectedly, work through
[reference/troubleshooting.md](reference/troubleshooting.md) — it maps the
platform's error messages (which are often misleading, e.g. OOM reported as
"startup timeout") to root causes and fixes.

In the handover summary, call out any items needing particular attention —
deferred TODOs, missing inputs, areas where assumptions were made, or sections
that may require manual review. Do not describe a running scheduled data product,
created vector table, or deployed mesh resource unless the command that created
or verified it actually ran successfully.
