---
name: nxd-query-data-product
description: Query a deployed Nextdata OS data product. Discovers the active mesh from local nxd settings, then does ALL discovery — data products, output ports, model attributes, health, glossary — through the mesh MCP gateway multiplexer in one session, not per-DP REST. Direct-store reads lease a credential from the per-DP REST API (the one thing the gateway cannot do) and route by output-port driver: SQL for relational stores (Snowflake, Postgres, BigQuery, Redshift, Databricks, DuckDB), presigned-URL fetch for file storage (S3, ADLS, GCS), vector similarity for vector stores (pgvector, Pinecone); RPC/MCP ports are called as gateway tools. Turns natural-language questions into concrete queries. Semantic questions — single-DP and cross-DP alike — go through the governed `run_semantic_query` tool; the platform compiles and executes, merging cross-DP joins server-side in the query system DP. Use when the user asks to "query a data product", "read from an output port", "search a named DP", or "join across data products".
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - AskUserQuestion
metadata:
  author: nextdata
  version: 0.36.2
---

# nxd data product query

Query a deployed Nextdata OS data product. The skill:

1. Finds the active mesh from `~/.nxd/meshes.json` (or `~/.nxd/config.yaml` as fallback).
2. Lists data products **via the MCP gateway** and asks the user which one (if not supplied).
3. Lists output ports + tools **via the MCP gateway** and asks the user which (if not supplied).
4. For a direct-store read, fetches the port's location and a leased credential from the DP REST API.
5. Routes the query by output-port driver type (or calls the MCP tool), then runs it.

## Gateway-first (discovery / metadata / health via MCP)

The mesh runs a single **MCP gateway multiplexer** (mcp-proxy-api) that serves —
over ONE MCP session — the catalogue, metadata, health, glossary, and debug info
this skill needs. **All discovery (Steps 2–4) goes through it, not REST.**
`scripts/gateway_tools.py` wraps the gateway tools (`tools/list` + `tools/call`
against `<base>/dp/mcp/`):

| Need | `gateway_tools.py` subcommand | Gateway tool |
|---|---|---|
| List data products | `list-dps [--domain D]` | `discovery…__list_data_products` |
| Output ports (+ infra service) + models/attributes | `details --dp <dp> --outputs --models` | `proxy__get_data_product_details` |
| Per-DP MCP/RPC tool list | `tools [--dp <dp>]` | `tools/list` |
| Health (diagnose a failing tool) | `health [--broken-only]` | `proxy__getDataProductsHealth` |
| Glossary | `glossary --name <gloss-dp>` | `glossary__get_glossary` |
| Logs / events (debug) | `logs --dp <dp>` / `events --dp <dp>` | `proxy__getDataProductLogs` / `…Events` |

**REST is used for ONE thing only: credential leasing + direct-store execution.**
The gateway has no credential-lease tool, so querying a relational / file /
vector port directly (Step 5 + 6a/6b/6c) goes through `connect_port.py` +
`query_sql.py` / `fetch_file.py` / `vector_search.py`. Everything REST discovery
used to do (`/data-products`, `/outputs`, `/models`) is now served by the gateway
— there is **no REST discovery fallback**. Run one gateway session per query;
re-list per query (the DP set + tools are not stable). Auth is the same token
used everywhere here (see **Credentials**): a PAT is sent on `X-Nextdata-Token`,
an OAuth session token on `Authorization: Bearer` — `mcp_http.py` picks the
header by token type automatically.

The public data product REST API contract the lease/query scripts drive is documented per-mesh at `<app_url>/docs/#/tutorials/guides/consumer-tutorial` (resolve `<app_url>` in Step 1; see **Platform docs**).

For **vector stores** and **MCP / RPC ports**, this skill consults the LLM (Claude — the conversation itself) to turn the user's natural-language question into a concrete query (vector similarity expression, MCP call payload) before executing.

This skill is read-only. It never writes to a data product's output store.

---

## Inputs the user can supply up-front

The user may pass any of these in the request — collect the rest interactively:

- **Mesh** — which configured mesh to query. nxd-setup-cli owns mesh selection; the active mesh + its api/app host come from `~/.nxd` (see Step 1). Do not hardcode a mesh host — derive it.
- **Data product** — `fullName` (illustrative example: `<dp-name>`, e.g. an embeddings DP). If missing, prompt with the list from `gateway_tools.py list-dps`. You can also scope by **domain** (`--domain`) when many DPs span domains — ask the user to narrow by domain rather than scrolling a long list.
- **Output port** — port `name` (illustrative examples: a `pgvector` port, an `adls` file port, a relational `*-out` port). If missing, prompt with `gateway_tools.py details --dp <dp> --outputs` (data ports) + `gateway_tools.py tools --dp <dp>` (MCP/RPC tools).
- **Infra-profile** — only needed when a port's `connect` returns `unsupported` (Step 5). Derive it from the port / mesh — `nxd ls infra-profiles` against the active mesh — or ask the user; do not assume a local file (see Step 5).
- **Query** — natural-language question, or a SQL string, or a vector-search description, or an MCP function + args. If missing, ask.

---

## Step 0: Make `scripts/` reachable from Bash (do this before anything else)

This skill is **script-first**, and some harnesses don't mount `scripts/` into the
Bash sandbox. Resolve a `WORKDIR` **once per session** (skill dir if Bash sees its
scripts, else a scratch copy) and run all later `scripts/...` commands + the
**Scripts** venv from it. Full recipe + rationale:
**[reference/scripts-bootstrap.md](reference/scripts-bootstrap.md)** — read before
Step 1. Quick probe:

```bash
[ -f "$SKILL_DIR/scripts/find_mesh.py" ] && WORKDIR="$SKILL_DIR"   # else bootstrap a copy
python3 "$WORKDIR/scripts/find_mesh.py" --help >/dev/null && echo "scripts reachable"
```

## Step 1: Locate mesh + auth

Mesh/env selection is the **first** thing this skill resolves — everything else (api host, doc links, infra-profile lookups) derives from it. nxd-setup-cli owns this config; this skill only reads it.

Read the user's local nxd settings. The mesh URL locates the gateway multiplexer + per-DP API; the token authenticates both (header by token type — see **Credentials**).

```bash
python3 scripts/find_mesh.py
```

`find_mesh.py` returns JSON like `{ "mesh_name": "...", "api_url": "...", "app_url": "...", "docs_base": "...", "token_available": true, "token_file": "..." }`. The token is written only to `token_file`, never stdout:

- Reads `~/.nxd/meshes.json` first (the registry the nxd-setup-cli skill maintains). The mesh **name**, `api_url`, `app_url`, and the auth/install host all come from the registry **entry** — never reconstructed from the host by label-count guesses.
- Falls back to `~/.nxd/config.yaml` — top-level `url:` and entries under `meshes:`.
- If multiple meshes are present, prints them and exits non-zero with a list. **Never guess the mesh** — do not infer it from the data product name or from where a DP "likely" lives. Resolve it two ways only: (1) if the config marks one mesh active (`config.yaml (active)`), use that one and re-run with `--mesh <name>`; (2) otherwise ask the user which one (use `AskUserQuestion`) and re-run with `--mesh <name>`.
- Token comes from the registry entry first; if absent, reads `~/.nxd/tokens.json` (the file `nxd login` writes). Tokens there are keyed by the OAuth auth host (`auth.<mesh>.<domain>`) — `find_mesh.py` matches the auth/install host carried by the mesh registry entry, falling back to an api-host domain match only when the registry omits it.
- Use the emitted `token_file` path as `$TOKEN_FILE` in later commands. The default token-file directory is the OS temp directory (`/tmp/...` on POSIX/WSL, `%TEMP%\...` on Windows), so do not hardcode `/tmp`.

If neither file is present or no usable token is found, tell the user to run the **nxd-setup-cli** skill first — and point them at the per-mesh setup docs at `<app_url>/docs/#/tutorials/cli/setup` (resolve `<app_url>` from `find_mesh.py`'s `app_url`; see **Platform docs** below).

**The MCP gateway requires a PAT — a plain OAuth session token 403s.** `find_mesh.py` only checks token *presence*, not type. A token from `nxd login` alone authenticates the DP REST API fine but is rejected by the gateway (`gateway_tools.py`, `mcp_call.py`) with 403. Check the token in `$TOKEN_FILE` starts with `nxdpat_`; if not, the user needs to mint one — `nxd create personal-access-token` or `nxd mcp config` (either mints/stores a PAT for the active mesh). This is a step **you cannot do on the user's behalf**; ask them to run it, then re-read `$TOKEN_FILE`.

**Token lifecycle / 401 recovery.** PATs in `~/.nxd/tokens.json` carry an `expiry`. The nxd CLI itself auto-refreshes the entry when any `nxd` command runs (e.g. `nxd whoami`); the skill's scripts only **read** the file, they do not refresh it. If a per-DP call returns `401 Unauthorized`, fail fast with a message telling the user to run any `nxd` CLI command (the simplest is `nxd whoami`) to refresh, then re-pull the catalogue. Do not silently drop endpoints that 401 — that turns into ghost data. The fix is one line: token file is regenerated from `~/.nxd/tokens.json` after the refresh and passed via `--token-file` to the next call.

### Platform docs (per-mesh)

Docs are served **per-mesh** from the active mesh's app host — there is no single global docs URL. Resolve the base from the mesh config (the `docs_base` / `app_url` that `find_mesh.py` prints), then append a path:

```
<app_url>/docs/#/<path>
```

It is a **docsify** site with hash (`#/`) routing — keep the `#/`, append the path **without** a `.md` extension. If a deep link 404s or shows a blank page, don't guess alternate paths: open the docs home `<app_url>/docs/#/` and navigate its sidebar, use the in-app Learn tab, or re-confirm the host from the mesh config. The doc paths most relevant to **querying / consuming** a data product:

| Topic | Path to append to `<app_url>/docs/#/` |
|---|---|
| Consuming another team's data product (REST API contract) | `tutorials/guides/consumer-tutorial` |
| Output ports | `tutorials/guides/02-outputs` |
| Semantic model (attributes / data types) | `tutorials/guides/01-semantic-model` |
| Inputs (request-model field semantics) | `tutorials/guides/04-inputs` |
| Promises & data quality | `tutorials/guides/03-promises` |
| Expectations (access / approval, DQ) | `tutorials/guides/05-expectations` |
| MCP (rpc-outputs / `nxd mcp client`) | `tutorials/guides/07-mcp` |
| CLI setup (mesh / auth) | `tutorials/cli/setup` |
| Create a data product & its infra profile | `tutorials/cli/create` |

Prefer **showing** over linking — a live `nxd ls …` / REST call against the user's mesh usually beats pointing at a page. Use the links to orient and fill gaps.

---

## Step 2: Pick the data product

If the user named one, validate it against the list. Otherwise present the list:

```bash
python3 scripts/gateway_tools.py list-dps [--domain <domain>] --token-file "$TOKEN_FILE"
```

Returns one entry per data product: `name`, `domain`, `description`, `status`, `endpoint`, plus access/promise stats. Use `AskUserQuestion` (single-select) when there are many; pass `--domain` (or the gateway tool's `filter_domain`) to narrow rather than scrolling an unscoped list.

Docs: the consumer REST API contract these calls follow is at `<app_url>/docs/#/tutorials/guides/consumer-tutorial`.

---

## Step 3: Pick the output port

List the data product's output ports and its MCP/RPC tools:

```bash
python3 scripts/gateway_tools.py details --dp <fullName> --outputs --token-file "$TOKEN_FILE"
python3 scripts/gateway_tools.py tools --dp <fullName> --token-file "$TOKEN_FILE"
```

`details --outputs` returns `outputs.ports[*]` — `name`, `infra_profile_name`, `infra_service_name`, `model_names`, `promises` (the same data-port contract the old REST `/outputs` gave, including the **driver / `infra_service_name` the credential-lease step in Step 5 needs**). `tools` returns the DP's MCP/RPC functions, namespaced `<function>__<hash>` on the multiplexer. Present data ports and RPC/MCP tools together, distinguished by kind. If only one port/tool exists, confirm and proceed; otherwise prompt the user.

Docs: output-port semantics (`/api/v1/outputs`, `/api/v1/rpc-outputs`) at `<app_url>/docs/#/tutorials/guides/02-outputs`.

---

## Step 4: Show the port's model attributes

Before the user submits a query, surface the column schema of the port's models so they can frame the question against real fields:

```bash
python3 scripts/gateway_tools.py details --dp <fullName> --models --token-file "$TOKEN_FILE"
```

`--models` (gateway `includeSemanticModels`) returns each model's `name`, `description`, and full `attributes` (`name`, `data_type`, `description`) with semantic/glossary links. Match the port's models (from Step 3's `outputs.ports[*].model_names` / `promises.model[].model`) against this list.

Render the attributes back to the user as a compact table (model → columns + types) and only then ask for the query. For natural-language queries against vector / RPC ports, also call out which column holds the text payload (vector store) or which `request_model` fields the query must populate (RPC).

Docs: to help the user interpret attributes / data types see `<app_url>/docs/#/tutorials/guides/01-semantic-model`; for request-model (input) field semantics see `<app_url>/docs/#/tutorials/guides/04-inputs`; the `port.promises.model[].model` resolution is explained at `<app_url>/docs/#/tutorials/guides/03-promises`.

---

## Step 5: Get port location + credentials

```bash
python3 scripts/connect_port.py --dp <fullName> --port <port> --api-url "$API_URL" --token-file "$TOKEN_FILE" --out <port_credentials_file>
```

`connect_port.py` writes to `--out` (never stdout) a JSON document with two keys:

- `location` — the result of `GET /api/v1/outputs/{port}/location`. Carries the data location (host/database/schema for SQL stores, account/container/model_paths for ADLS, bucket/prefix for S3, etc.).
- `connect` — the result of `POST /api/v1/outputs/{port}/connect` with `{"ttl":"<ttl>"}` (default `PT1H`). Returns one of:
  - `status: "connected"` with `leased_credential` (presigned URLs, DB creds, etc.).
  - `status: "approval_pending"` with an approval form — surface the message and `tracking_url` to the user and stop. The access / approval and data-quality expectation model is documented at `<app_url>/docs/#/tutorials/guides/05-expectations`.
  - `status: "unsupported"` — driver does not lease credentials. You then need an **infra-profile** to construct auth out-of-band. **Derive or elicit it — do not assume a local file exists:**
    1. Read the `infra_profile_name` / `infra_service_name` the port declares (from `gateway_tools.py details --dp <dp> --outputs` in Step 3).
    2. Resolve the profile against the **active mesh** — `nxd ls infra-profiles` lists what the mesh actually has; confirm the matching profile with the user.
    3. Only if the user genuinely has a working-tree copy from the **nxd-build-data-product** skill, you may read the infra-profile YAML on disk — but **ask the user to confirm the path first**, don't grep assumed directories. How DPs and their infra-profiles are defined is documented at `<app_url>/docs/#/tutorials/cli/create`.
    4. If neither resolves, ask the user for the infra-profile name (`AskUserQuestion`) rather than guessing.

**Never echo credentials to the chat.** Read `<port_credentials_file>` with `Read`, but only render the location fields back to the user. Pass the file path to the query scripts that need credentials; they read it themselves.

---

## Step 6: Route the query by driver and execute

The infra-service driver (from the port's `infra_service_name` in the infra profile, or from the `leased_credential.details.type_hint` when present) decides which path runs. If **neither** is present, do not assume a driver — resolve the profile from the mesh (`nxd ls infra-profiles` against the active mesh) or ask the user which service the port targets (`AskUserQuestion`).

### 6a. Relational SQL — Snowflake, Postgres, BigQuery, Redshift, Databricks-SQL, DuckDB

The leased credential carries `username`, `password` / `private_key`, plus the location's `host`, `port`, `database`, `schema`. Run SQL via:

```bash
python3 scripts/query_sql.py --creds <port_credentials_file> --sql "<SQL>"
```

If the user asked in natural language, **you (Claude)** generate the SQL from the port's `model_names` plus the model schemas already fetched in Step 4 (`gateway_tools.py details --dp <dp> --models`) — embed those attributes into the SQL you draft. Show the user the SQL you intend to run before running it; only run after they confirm. Cap rows with `LIMIT` and only read the schema/table the location names.

### 6b. File storage — S3, ADLS, MinIO, GCS

The leased credential includes `model_urls` (presigned URLs, per model) — one per output model. The location lists `model_paths` with the on-disk format (`parquet`, `csv`, `json`, …).

```bash
python3 scripts/fetch_file.py --creds <port_credentials_file> --model <model_name> --limit 50
```

`fetch_file.py` downloads the presigned URL into memory, parses the file by format, and writes a small preview JSON to stdout (head + schema). For a real query (filter / aggregate / project), generate SQL and run it via `duckdb` against the downloaded file — `fetch_file.py` supports a `--sql` flag that loads the file as a DuckDB table and executes the SQL.

### 6c. Vector store — pgvector, Pinecone (classic RAG pipeline)

Vector ports run as a small RAG pipeline: the LLM (Claude) is the generator;
`embed_query.py` + `vector_search.py` are the retriever (rewrite → embed →
retrieve [vector-only / hybrid RRF] → abstain → generate → optional agentic
loop). This path needs leased credentials (no MCP equivalent), so it stays on
the REST `connect_port.py` lease. **Full step-by-step pipeline, flags, and
thresholds: [reference/vector-rag.md](reference/vector-rag.md).**

### 6d. RPC / MCP port

RPC / MCP tools are served through the **gateway multiplexer** — discover and
call them there, not via the REST `/rpc-outputs` contract. The MCP guide is at
`<app_url>/docs/#/tutorials/guides/07-mcp`.

**Consult the LLM.** The user's natural-language question maps onto one of the data product's tools:

1. List the DP's tools (names, descriptions, input schemas) — already in hand from `gateway_tools.py tools --dp <fullName>` (Step 3), each named `<function>__<hash>` on the multiplexer.
2. Pick the tool that matches the user's intent (you, Claude, do this).
3. Construct the request payload conforming to the tool's `inputSchema`.
4. Call it through the multiplexer:

```bash
python3 scripts/mcp_call.py \
  --endpoint "<base>/dp/mcp/" --tool "<function>__<hash>" \
  --args '<json>' --token-file "$TOKEN_FILE" --out <out_file>
```

5. Show the response to the user; for natural-language answers, synthesise from the response payload.

`mcp_call.py` opens one MCP session, calls the tool, and writes the unwrapped result to `--out`. (Interactive `nxd mcp client` is still available when a user explicitly wants a live MCP session, but one-shot calls go through `mcp_call.py`.)

#### Semantic-layer MCP ports (`list_models` / `run_semantic_query`)

A data product built with the **nxd-build-semantic-data-product** skill exposes a governed
text-to-SQL surface as four RPC functions: `list_models`, `describe_model`,
`run_semantic_query`, and `semantic_model` (raw per-model registry projection,
including any `to_data_product` cross-DP join edges the DP publishes). Treat the
first three as a discover→select→run protocol, not free-form SQL:

1. **Discover — `list_models`.** Call `list_models` first to see the available
   semantic models (entities), their grains, and how they join. Never guess
   concept names or grain membership — the listing is the canonical source.
2. **Select — `describe_model(name)`.** For each model you intend to query,
   call `describe_model` with its name. The response contains:
   - **metrics** (each with its `compatible_dimensions` list — the dimensions
     that share the model's grain),
   - **dimensions** (with PII classifications),
   - **joins** (with a `reaches_dimensions` list — dimensions reachable through
     the join without grain-hopping).
   Call `describe_model` once per model; do not batch models into a single call.
3. **Run — `run_semantic_query` by concept name, never SQL.** Takes a
   `{measures, dimensions, filters}` payload of concept names (e.g.
   `{"measures": ["total_revenue"], "dimensions": ["country"]}`). Do NOT pass a
   `sql` key or a raw SQL string — the DP compiles the selection itself and
   returns the `compiled_sql` (aggregated, read-only, row-capped) plus rows.
4. **Grain-safe navigation.** Because each `describe_model` response is exactly
   one grain, grain boundaries are visible before you query. Combining measures
   from **join-reachable** models in ONE `run_semantic_query` call is safe — the
   compiler pre-aggregates each measure at its own grain before joining, so
   joinable models never double-count (fan-out-safe). Only measures whose grains
   are NOT connected by any documented join are incompatible and raise a
   `CompileError` at compile time; for those, issue one query per model and
   present the result sets separately.

**Cross-DP questions — `run_semantic_query` still, on the platform query DP.**
When a question spans models owned by DIFFERENT data products (e.g. a metric on
DP A grouped by a dimension on DP B, joined through a crosswalk), do NOT harvest
and merge per-DP registries yourself, and do NOT call a member DP's own
`run_semantic_query` (it only knows its own registry). Call the platform's
built-in cross-DP tool on the mesh MCP gateway:
**`query-system-dp-<env>__run_semantic_query`** (confirm the exact wire name via
`gateway_tools.py tools` — it is a proxy built-in, so it appears in the gateway
`tools/list` without a `__<hash>` suffix). The query system DP harvests every
entitled member's registry, merges them into one cross-DP registry (using each
join's `to_data_product` owner edge), authorization-gates each touched member,
resolves per-member warehouse credentials, and compiles + executes ONE
fan-out-safe cross-DP JOIN server-side. The request is identical to a single-DP
call — `{measures, dimensions, filters, order_by, limit}` of concept names — the
merge/gate/execute all happen platform-side. Discover the mesh-wide concept
vocabulary with the same built-in `query-system-dp-<env>__{list_models,
describe_model}` tools.

Call all these functions exactly like any other MCP tool — `mcp_call.py` against
the multiplexer (§6d above), using the wire name from `gateway_tools.py tools`.

### 6e. External API ports — `driver: api`

The location is a URL; the leased credential is whatever the upstream API needs (bearer, basic, key). Build the HTTP call from the model schema, run it via `curl` or `python -m requests`.

### 6f. Semantic query layer — the intent gate

Builds on §6d's discover→select→run protocol for the three semantic tools, adding
the **intent gate** between selection and execution (rationale: [reference/semantic-intent-validation.md](reference/semantic-intent-validation.md)).
The compiler is deterministic and fan-out-safe, so once the **selection**
(`{measures, dimensions, filters}`, §6d) is right the number is right; the only
remaining risk is whether it captured what the user asked. The gate confirms that
first, reading only `describe_model` metadata (`metrics` with
`compatible_dimensions`, `dimensions` with PII flags, `joins` with
`reaches_dimensions`) — no extra server surface.

**Intent gate (REQUIRED before `run_semantic_query`).** Run all three:

1. **Critic (catalog-aware).** From the *verbatim* question + selection +
   `describe_model` metadata, return a verdict (`ok` / `ambiguous` / `likely-wrong`)
   and suspect concepts. Check each metric's `description` matches intent (e.g.
   `sales_calls`, not `call_count`), and each chosen dimension is in the metric's
   `compatible_dimensions` **or** a join's `reaches_dimensions` (neither → the
   compiler rejects it; catch it here).
2. **Echo (round-trip restatement).** Restate the selection in plain language from
   `describe_model` — *"<metric.description>, per <dimension.description>, filtered
   where <dimension.description> <op> <value>"* — using each metric's `description`
   as-is (don't re-prefix the raw `aggregation`). PII-flagged dimension → note it's
   governed / maskable. Deterministic: same selection → same echo.
3. **Clarify (don't guess).** Critic `ambiguous` / `likely-wrong`, **or** a chosen
   dimension neither `compatible` nor reachable → `AskUserQuestion` listing the real
   candidates from `list_models` / `describe_model`; do **not** execute until
   resolved. Abstain beats a confident wrong number.

**Execute** only after the gate passes (critic `ok` / user confirmed). The response
carries `compiled_sql`, `rows`, `row_count`, `truncated`, `error`; on non-empty `error`, map via the troubleshooting table (mixed-grain → one query per model), don't retry blindly.

> **Not built here:** self-consistency vote (deferred) and value-linking
> (server-side — grounding a filter *value* to its stored form needs a warehouse
> `DISTINCT` read, not reachable from the three tools). See the [README](README.md)
> for both; the value-mismatch symptom is the table row below.

---

## Credentials on the command line

**Never put a bearer token or password on a command line.** The scripts read secrets from one of:

- `stdin` — pipe the token in: `echo "$TOK" | python3 scripts/connect_port.py …`
- `--token-file <path>` — a file containing the token. Prefer the `token_file` emitted by `find_mesh.py`.
- A JSON credentials file (`--creds <port_credentials_file>`) — the leased credential blob produced by `connect_port.py`.

The skill itself never prints tokens, presigned URLs, or DB passwords back to the chat. When showing the user what was leased, show the *fields available* (e.g. `presigned_url`, `database`, `schema`) — not the values.

**Token + header by surface.** The same token file feeds both surfaces, but the
wire header differs and `mcp_http.py` / `nxd_api.py` handle it for you:

- **MCP gateway** (`gateway_tools.py`, `mcp_call.py`) — requires a **PAT**
  (`nxdpat_…`, minted via `nxd create personal-access-token` / `nxd mcp config`)
  sent on **`X-Nextdata-Token`** — the only auth the gateway accepts. A plain
  OAuth session token (from `nxd login`) 403s here even though it authenticates
  fine against REST — see **Step 1** and the troubleshooting table.
- **DP REST API** (`list_*`, `connect_port.py`, …) — accepts either token kind on `x-nextdata-token`.

A `401` on either surface means the token is missing/expired: refresh a PAT
(`nxd mcp config`) or an OAuth session token (`nxd whoami`), then retry. A
`403` on the gateway with a token that works against REST means the token is
the wrong *kind*, not expired — mint a PAT (see Step 1).

---

## Scripts

The skill ships small Python entrypoints under `scripts/`. Resolve `$WORKDIR`
first (**Step 0**), then install dependencies into a throwaway venv (Windows:
`py -3 -m venv` + `.\...\Scripts\pip.exe`):

```bash
python3 -m venv .nxd-query-data-product-venv
.nxd-query-data-product-venv/bin/pip install -r "$WORKDIR/scripts/requirements.txt"
```

| Script | Purpose |
|---|---|
| `gateway_tools.py` | **The discovery path (MCP-only).** One multiplexer session → `list-dps`, `details` (outputs/models/inputs/promises/policies), `health`, `glossary`, `logs`, `events`, `tools`. This is the sole discovery surface — the old REST `list_dps.py` / `list_outputs.py` / `port_models.py` are removed |
| `find_mesh.py` | Discover the active mesh URL and bearer token from `~/.nxd/` |
| `connect_port.py` | `GET /location` + `POST /connect` — fetch port location + leased credential (no MCP equivalent — required for direct-store query) |
| `query_sql.py` | Run a SQL query against the leased database credential |
| `fetch_file.py` | Download a leased presigned URL, preview / SQL-query the file with DuckDB |
| `embed_query.py` | Compute an embedding for a query string using a named model |
| `vector_search.py` | Vector similarity search against pgvector / Pinecone |
| `mcp_http.py` | Minimal MCP Streamable-HTTP client — the shared transport under `gateway_tools.py` + `mcp_call.py` (handles `initialize`, session id, `tools/list`, `tools/call`) |
| `mcp_call.py` | One-shot CLI over `mcp_http.call_tool_one_shot` — opens an MCP session, calls one tool, writes the unwrapped result to `--out`. Used for RPC/MCP calls (§6d), single-DP `run_semantic_query` (§6f), and the platform cross-DP `query-system-dp-<env>__run_semantic_query` built-in (§6d) |

Each script writes secrets only to `--out` files (never stdout) and reads tokens via `--token-file` or stdin.

---

## Gotchas

- **Token expiry** — `tokens.json` carries an `expiry`. If a 401 comes back, ask the user to re-run `nxd login` (or the **nxd-setup-cli** skill) and retry. Per-mesh auth/PAT setup is documented at `<app_url>/docs/#/tutorials/cli/setup`.
- **`connect` returns `unsupported`** — derive the infra-profile from the active mesh (`nxd ls infra-profiles`) or ask the user; only read an on-disk infra-profile YAML if the user confirms they have a working-tree copy (e.g. from `nxd-build-data-product`) and confirms the path. Do not grep assumed directories. See `<app_url>/docs/#/tutorials/cli/create`.
- **`connect` returns `approval_pending`** — stop and surface the `message` / `tracking_url` to the user. Do not poll.
- **Long-lived presigned URLs** — every `connect` call returns fresh credentials with a fixed TTL. Cache the response in `<port_credentials_file>` for the session; re-request if the TTL passes.
- **Vector store embedding model mismatch** — querying with a different embedding model from the one the data product used to index gives nonsense results. Always confirm the model from the data product's `description` before computing the query vector — read it through the gateway (`gateway_tools.py details --dp <dp>`), the same source as every other discovery here.
- **Local `*.nxd.local` cluster + `requests` SSL errors despite a correct CA bundle** — `REQUESTS_CA_BUNDLE` pointed at the cluster CA (`shared/charts/nxd/localCerts/nxdCA.crt`) is the right first fix, but Python `requests` can still fail TLS verification against a local cluster even when `curl` against the same host succeeds. If `requests` still errors after confirming the bundle path, set `NXD_MCP_INSECURE=1` (skips TLS verification in `mcp_http.py` — local dev only, never against a real mesh).
- **`find_mesh.py --mesh <name>` fails but a `config.yaml.<name>` file exists** — a saved-but-inactive config variant isn't the same as a registered mesh; `find_mesh.py` only reads `meshes.json` + the *active* `config.yaml` (no `--config` flag). Copy `~/.nxd/config.yaml.<name>` over `~/.nxd/config.yaml` to make it active, then re-run. If the mesh is still unreachable after that, it's a network problem (VPN) between you and that mesh — a prerequisite this skill can't fix.
- **One gateway session per query** — the DP set + each DP's tools change (new DP, redeploy, breaker flip). Don't reuse a tool list across queries; re-run `gateway_tools.py` per question. Use `nxd mcp client` only when the user explicitly wants an interactive MCP session.
- **Cross-DP join not resolvable** — if `query-system-dp-<env>__run_semantic_query` returns a `CompileError` "no join path connects model X to model Y", the two models are not linked by any published join edge. A cross-DP edge only exists when the owning DP's `semantic_model` declares the join with a `to_data_product` marker (the crosswalk/fact DP publishes it, not the target). The right answer is "these concepts aren't joinable in the mesh" — do NOT hand-write a join or guess from column names. Add the missing `to_data_product` join edge to the source DP's model and redeploy, or ask the user to narrow the question.

---

## Troubleshooting query-time failures

Symptom → cause → fix for failures hit while querying a port lives in
**[reference/troubleshooting.md](reference/troubleshooting.md)** (auth/TTL 401·403,
`connect` `unsupported`/`approval_pending`, vector model/dimension mismatch,
pgvector 0-rows, RPC 404, and the `run_semantic_query` grain/dimension/value-match
cases). Diagnose before retrying — the same symptom (e.g. an empty result) has
more than one cause. When the failure is the data product itself (port unhealthy,
no data, RPC pod crashing) rather than the query, switch to the
**nxd-debug-data-product** skill.
