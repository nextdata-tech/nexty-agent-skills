---
name: nxd-data-product-query
description: Query a Nextdata OS Data Product through its REST API. Discovers the active mesh from the user's local nxd settings, lists Data Products and their output ports, fetches each port's location and a leased credential from the Data Product's REST API, then runs the user's query against the port using credentials returned by the platform. Routes by service type — SQL for relational stores (Snowflake, Postgres, BigQuery, Redshift, Databricks, pgvector metadata), presigned-URL fetch for file storage (S3, ADLS), vector similarity for vector stores (pgvector, Pinecone), and MCP/RPC calls for RPC ports — and consults the LLM (Claude) to translate natural-language questions into the right query for vector stores and MCP endpoints. Also supports a strict MCP-only mode that disables direct-store access, discovers DP MCP endpoints through the mesh MCP gateway, builds a plan from semantic_model relationships, runs the plan through an independent validator, and only executes if validation passes. Use when the user asks to "query a data product", "read from an output port", "search a named DP", "fetch the latest rows from a named DP", "use strict mode", "MCP-only", or similar.
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - AskUserQuestion
metadata:
  author: nextdata
  version: 0.1.0
---

# nxd Data Product Query

Query a deployed Nextdata OS Data Product through its public Data Product REST API. The skill:

1. Finds the active mesh from `~/.nxd/meshes.json` (or `~/.nxd/config.yaml` as fallback).
2. Lists Data Products on the mesh and asks the user which one (if not supplied).
3. Lists output ports on that Data Product and asks the user which port (if not supplied).
4. Fetches the port's location and a leased credential from the DP API.
5. Routes the query by output-port driver type, then runs it.

The public Data Product REST API contract this skill drives is documented per-mesh at `<app_url>/docs/#/tutorials/guides/consumer-tutorial` (resolve `<app_url>` in Step 1; see **Platform docs**).

For **vector stores** and **MCP / RPC ports**, this skill consults the LLM (Claude — the conversation itself) to turn the user's natural-language question into a concrete query (vector similarity expression, MCP call payload) before executing.

This skill is read-only. It never writes to a data product's output store.

---

## Inputs the user can supply up-front

The user may pass any of these in the request — collect the rest interactively:

- **Mesh** — which configured mesh to query. nxd-setup owns mesh selection; the active mesh + its api/app host come from `~/.nxd` (see Step 1). Do not hardcode a mesh host — derive it.
- **Data Product** — `fullName` (illustrative example: `<dp-name>`, e.g. an embeddings DP). If missing, prompt with the list returned by `/api/v1/data-products`. You can also scope by **domain** (the `domain` field in the DP list) when many DPs span domains — ask the user to narrow by domain rather than scrolling a long list.
- **Output port** — port `name` (illustrative examples: a `pgvector` port, an `adls` file port, a relational `*-out` port). If missing, prompt with the list returned by `/api/v1/outputs` on that DP.
- **Infra-profile** — only needed when a port's `connect` returns `unsupported` (Step 5). Derive it from the port / mesh — `nxd ls infra-profiles` against the active mesh — or ask the user; do not assume a local file (see Step 5).
- **Query** — natural-language question, or a SQL string, or a vector-search description, or an MCP function + args. If missing, ask.
- **Strict mode** (`--strict`) — opt-in MCP-only mode. When the user asks for "strict mode", "MCP-only", "no direct access", or passes the flag explicitly, follow **Strict Mode** below instead of the default routing in Step 6. Strict mode disables every data-source-direct path (SQL, presigned-URL fetch, pgvector dial, external API) and only allows mediated access via MCP.

---

## Strict mode (MCP-only, plan-verified)

A locked-down mode for queries that must demonstrably go through MCP and nothing else. The rules below are declarative — satisfy them however the flow works out per request; do not treat the list as execution order.

### Rules
1. **Data access only via MCP endpoints exposed by Data Products.** Do not authenticate against or call any underlying data source directly (no Snowflake/Postgres/pgvector dial, no presigned-URL fetch, no external API call). Discover available DP MCP endpoints through the **mesh-level MCP gateway** — a per-mesh endpoint that lists every DP MCP server registered on the mesh and the functions each exposes. Resolve its URL from the mesh config the same way Step 1 resolves the api/app host (see `mcp_gateway.py`).
2. **Semantic relationships only via the `semantic_model` MCP endpoints.** Some DPs expose a `semantic_model` MCP function that returns model attributes plus typed relationships to models in **other** DPs (foreign keys, derived-from, joins-on). For any cross-DP reasoning use **only** these endpoints; never infer relationships from column-name heuristics, embedding-space similarity, or memory.

> **Only `semantic_model` is standard.** Every other MCP tool name on a DP — search, get, scan, top-k, custom RPCs — is author-defined and may change. The skill must learn every non-`semantic_model` tool from a **live** gateway call, never from a hard-coded list, doc reference, or prior run.

> **Re-fetch every query.** The set of DPs, their MCP endpoints, and the tools each one publishes can change at any time (new DP launched, schema rev, breaker flips, redeploy). Run `mcp_gateway.py` and `semantic_relations.py` again **for every user query** — do not reuse a catalogue from an earlier conversation, an earlier turn, or any on-disk cache older than the current question. If a previous file is on disk, delete it or overwrite it; treat the catalogue as session-scoped, query-scoped data.
3. **Plan-first, human-readable.** Process every user question by first building a written **query plan** that covers the full execution — including multi-DP / multi-endpoint paths — and the **provenance** of each step: which MCP function the step calls, which `semantic_model` response justified each join / projection / filter, and which user-question phrase mapped onto each parameter. The plan is text the user can read end-to-end before anything runs.
4. **Validated before execution.** Every plan goes through an independent **plan validator** that checks (a) every relationship asserted in the plan is present in at least one `semantic_model` MCP response collected this session, (b) every data-fetching step targets an MCP endpoint listed by the gateway, and (c) no step calls a non-MCP path (raw SQL against a port, direct presigned-URL fetch, direct HTTP to an external API).
5. **Execute only if validation passes.** On pass: run the plan via MCP calls and return `{plan, validation_report, results}` to the user. On fail: return the plan, the validation failures, and a short explanation — **do not run any step**.

### Discovering MCP functions per DP (two-stage)

The gateway tells you which DP MCP **endpoints** exist on the mesh; it does **not** tell you which functions each endpoint exposes. To learn the per-DP function list, do this two-stage discovery — every query, no cache.

**Stage 1 — endpoint list (CLI).** Run `nxd mcp health --format json`. It wraps `GET /health/dps` on mcp-proxy-api and returns one row per registered DP MCP endpoint with URL, `derived_state`, breaker state, and a reported `tool_count` — **not** the tool names. Skip rows whose `derived_state` is `Broken` (breaker Open) unless explicitly probing.

```bash
nxd mcp health --format json
```

**Don't pass `--mesh` blindly.** When `~/.nxd/config.yaml` has a name that appears both top-level (the `url:` field) and inside the `meshes:` block, `nxd mcp health --mesh <name>` picks the entry under `meshes:` — which may not be the active one — and silently queries the wrong proxy host. The robust recipe is to **omit** `--mesh` in the default case so the CLI uses the top-level active `url:`. Only pass `--mesh <name>` when the user has explicitly asked for a non-active mesh and the name resolves unambiguously. `mcp_gateway.py` already follows this rule: it propagates `--mesh` only when the caller passed one.

**Stage 2 — tool names + schemas (MCP Streamable-HTTP).** For each healthy endpoint URL from Stage 1, open a short MCP session and call `tools/list`. The CLI doesn't expose this, so `scripts/mcp_http.py` does the minimal protocol:

1. `POST <endpoint>/` with JSON-RPC `initialize` → `200` + `Mcp-Session-Id` response header.
2. `POST` `notifications/initialized` (no id) → `202` ack.
3. `POST` JSON-RPC `tools/list` with `Mcp-Session-Id` header → returns `[{name, description, inputSchema}, …]`.

Bearer: PAT from `~/.nxd/tokens.json` (written by `nxd login`). The same token works against the proxy host since auth + proxy share a parent domain.

**Glue:** `scripts/mcp_gateway.py` runs Stage 1 via subprocess, then loops the endpoints calling Stage 2 via `mcp_http.McpClient`, and writes one catalogue JSON with `endpoints[*].tools[*].{name, description, input_schema}` plus a flat `function_index` of `(dp, tool)` pairs.

```bash
python3 scripts/mcp_gateway.py --token-file /tmp/strict-tok.txt --out /tmp/strict-gw.json
```

**What the catalogue gives you, by function class:**

| Class | How to identify it in the catalogue | What it returns | Use it for |
|---|---|---|---|
| **(a) Data-returning functions** | Any tool whose name does **not** match `^semantic[_-]?models?$` — search/get/scan/top-k/custom RPCs the DP author defined | Domain data (rows, ranked chunks, aggregates, summaries). Shape is whatever the DP author published | Plan steps that fetch data |
| **(b) Semantic-model functions** | Tool whose name matches `^semantic[_-]?models?$` | A list of model attributes plus typed relationships / links to models in **other** DPs (`SameAs`, `Derived`, `joins_on`, `fk`) | Plan Validation Rule 2 / Rule 4 — every cross-DP join / projection / filter must trace back to an entry returned here. Run via `scripts/semantic_relations.py` |

Only the **(b)** name is standard. Everything in **(a)** is author-defined and may change between runs — that is why both stages are re-fetched per query.

### Flow (one shape that satisfies the rules)

1. **Discover MCP surface.** Call the mesh MCP gateway to enumerate DP MCP endpoints and their declared functions. Cache the gateway response per session.
   ```bash
   python3 scripts/mcp_gateway.py --api-url "$API_URL" --out /tmp/nxd-mcp-gateway.json
   ```
2. **Collect semantic models.** For each candidate DP that exposes a `semantic_model` MCP function, call it and collect the returned model attributes + cross-DP relationships into a single relations bundle. Candidates are the DPs whose descriptions / function names plausibly relate to the user's question — narrow by domain when there are many.
   ```bash
   python3 scripts/semantic_relations.py --gateway /tmp/nxd-mcp-gateway.json --dps <fullName>,<fullName>,… --out /tmp/nxd-relations.json
   ```
3. **Draft the plan (LLM, in the conversation).** Using the gateway + relations bundle, write a human-readable plan with these sections:
   - **Question** — the user's question, verbatim.
   - **Candidate sources** — which DP MCP endpoints are relevant and why (one line each, citing the gateway entry / `semantic_model` response that justified inclusion).
   - **Steps** — ordered execution steps. Each step lists: DP `fullName`, MCP function name, request payload, expected response shape, and which relations bundle entry (if any) justified the join/projection/filter.
   - **Joins & relationships** — every cross-DP join or relationship the plan relies on, with a pointer to the `semantic_model` MCP response (DP + path) that declares it.
   - **Provenance** — for each step, which phrase of the user question mapped onto which parameter.
   - **Open questions / assumptions** — anything the relations bundle didn't fully cover.
4. **Validate the plan.** Run the validator over the plan + the cached gateway + relations bundle:
   ```bash
   python3 scripts/plan_validator.py --plan /tmp/nxd-plan.json --gateway /tmp/nxd-mcp-gateway.json --relations /tmp/nxd-relations.json --out /tmp/nxd-validation.json
   ```
   The validator emits `{passed: bool, checks: [...], failures: [...]}`. Failures categorise as `unknown_relationship`, `non_mcp_step`, `unknown_endpoint`, `unknown_function`, `unsupported_param`.
5. **Execute or abstain.**
   - If `passed=true`: walk the plan and run each step via `rpc_call.py --mcp …` (or the gateway client). Collect responses and return `{plan, validation_report, results}` to the user.
   - If `passed=false`: return `{plan, validation_report}` with each failure named and the rule it violated (Rule 1 / 2 / 4). **Stop.** Do not retry the underlying query through a non-MCP path; if the user wants to relax strict mode, they pass `--strict=false` (or "drop strict mode") and the skill falls back to the default Step-6 routing.

### Plan format (shape on disk)

`/tmp/nxd-plan.json`:

```json
{
  "question": "…verbatim user question…",
  "candidate_sources": [
    {"dp": "<fullName>", "mcp_function": "<fn>", "reason": "…", "evidence": {"gateway_entry": "…"}}
  ],
  "steps": [
    {
      "id": "s1",
      "dp": "<fullName>",
      "mcp_function": "<fn>",
      "request": {"…": "…"},
      "expected_response_shape": "…model name or schema ref…",
      "depends_on": [],
      "join_basis": null
    }
  ],
  "relationships_used": [
    {"from_dp": "<A>", "from_model": "<m1>", "to_dp": "<B>", "to_model": "<m2>", "kind": "fk|derived|joins_on", "evidence": {"semantic_model_dp": "<A>", "path": "relationships[0]"}}
  ],
  "provenance": [{"step_id": "s1", "param": "from", "phrase": "…", "source": "user_question"}],
  "assumptions": ["…"]
}
```

### Plan Validation

The validator runs **independently** of the plan generator. Treat plan generation and plan validation as two separate actors with separate inputs:

- **Generator inputs** — the user question, the gateway catalogue, the relations bundle, prior conversation context, scratch notes, embedding-space hunches, anything Claude reasoned through to pick steps. Generator emits the plan JSON; that JSON is the **only** thing the validator may consume from the generator.
- **Validator inputs** — the emitted plan JSON, and a *fresh* read of the gateway catalogue + relations bundle from disk. The validator must **not** read the generator's chain of thought, the prior turn's notes, any LLM reasoning, or anything else the generator used to build the plan. If a fact does not survive serialisation into the plan, it does not exist for the validator.
- **Same files, fresh load.** The validator opens `gateway.json` / `relations.json` itself rather than receiving them from the generator. This catches generator drift: a plan that referenced a tool the generator "remembered" but never wrote into the plan, or a relationship the generator inferred but never recorded under `relationships_used`, will fail validation here.

Concrete checks the validator runs:

- For every `relationships_used[*]`: an entry must exist in `relations.json` whose `from_dp/from_model/to_dp/to_model/kind` matches; the `evidence.semantic_model_dp` must be the DP that returned it.
- For every `steps[*]`: `dp + mcp_function` must appear in `gateway.json`'s function index.
- No step may carry a `direct_sql`, `presigned_url`, or `http_request` field — those tag non-MCP paths and fail the run.
- Every `steps[*].request` field must reference either (a) a literal from `provenance`, (b) the output of a `depends_on` step, or (c) a value drawn from `relationships_used`. Unbound params fail.

**Generator ↔ validator retry loop.** On `passed=false`, surface the structured `failures[]` back to the generator with each entry's `check`, `step_id`, and `detail`. The generator rewrites the plan to address the named gaps — add a missing `relationships_used[*]` and back it with a real `relations.json` entry, swap an unknown tool for one in the gateway, bind an unbound param, drop a non-MCP field — and the validator re-runs over the new plan. Cap the loop at **3 attempts** to bound cost.

**Hard fail if no valid plan is reachable.** If the generator cannot produce a plan that the validator passes within the retry cap, **the query fails**. Do not run any step. Return to the user: the final attempted plan, the validator's failure list from the last attempt, and a short explanation that points to whichever of these is the root cause: (a) the gateway catalogue has no tool that can answer the question, (b) `relations.json` lacks a relationship the question requires, (c) the question needs data not exposed by any reachable DP. Tell the user what would have to change on the mesh side (add a tool, publish a relationship in a `semantic_model` response, fix a Broken endpoint) for the same question to succeed next time.

**Known limitation — structural only.** Plan Validation verifies that declared relationships *exist* in `semantic_model` responses; it does **not** verify that the underlying values on the two sides of a relationship actually intersect at runtime. A `SameAs` between `A.x` and `B.y` can pass validation while every per-row fan-out returns zero because the identifier encodings diverge or the value sets are disjoint. Symptom during execution: per-row queries return empty / zero while the same tool called without that filter returns non-zero — that's the data-level mismatch fingerprint.

When that pattern appears in results, surface it explicitly to the user; do not retry with alternate encodings (that's hallucination). The fix lives on the mesh side: either correct the `semantic_model` link (e.g. `SameAs` → `Derived` with the actual transform), or fix one side's stored values. The skill may optionally implement a Rule-6 runtime probe that, before fan-out execution, samples N distinct values from each side of a relationship via the available data tools, intersects them, and abstains when the intersection is empty — this catches the class of bug at plan-time rather than after a fruitless execution. Implement only when the source DP exposes a tool that returns distinct values cheaply.

### Abstain rules

- Mesh MCP gateway not reachable → strict mode cannot run. Tell the user; do not silently fall through.
- No candidate DP exposes a `semantic_model` MCP function for the model the user is asking about → cross-DP reasoning is not possible in strict mode. Return the gateway + relations bundle gathered so far and stop.
- Plan needs a step that is not declared in any DP's MCP function list → validation fails with `unknown_function`; do not invent.

### Output the user sees

A single response with three parts, in order: the **plan** (human-readable, the text of the JSON above rendered as prose + a table of steps), the **validation report** (pass/fail + each check), and, if validation passed, the **results** (one block per step, with MCP function + response excerpt). If validation failed, the third part is replaced by an "Execution skipped" notice citing the rule numbers that were violated.

---

## Step 1: Locate mesh + auth (do this first)

Mesh/env selection is the **first** thing this skill resolves — everything else (api host, doc links, infra-profile lookups) derives from it. nxd-setup owns this config; this skill only reads it.

Read the user's local nxd settings. The mesh URL is needed to list Data Products; the bearer token is needed to call the per-DP API.

```bash
python3 scripts/find_mesh.py
```

`find_mesh.py` returns JSON `{ "api_url": "...", "app_url": "...", "docs_base": "...", "token": "..." }`:

- Reads `~/.nxd/meshes.json` first (the registry the nxd-setup skill maintains). The mesh **name**, `api_url`, `app_url`, and the auth/install host all come from the registry **entry** — never reconstructed from the host by label-count guesses.
- Falls back to `~/.nxd/config.yaml` — top-level `url:` and entries under `meshes:`.
- If multiple meshes are present, prints them and exits non-zero with a list. **Never guess the mesh** — do not infer it from the Data Product name or from where a DP "likely" lives. Resolve it two ways only: (1) if the config marks one mesh active (`config.yaml (active)`), use that one and re-run with `--mesh <name>`; (2) otherwise ask the user which one (use `AskUserQuestion`) and re-run with `--mesh <name>`.
- Token comes from the registry entry first; if absent, reads `~/.nxd/tokens.json` (the file `nxd login` writes). Tokens there are keyed by the OAuth auth host (`auth.<mesh>.<domain>`) — `find_mesh.py` matches the auth/install host carried by the mesh registry entry, falling back to an api-host domain match only when the registry omits it.

If neither file is present or no usable token is found, tell the user to run the **nxd-setup** skill first — and point them at the per-mesh setup docs at `<app_url>/docs/#/tutorials/cli/setup` (resolve `<app_url>` from `find_mesh.py`'s `app_url`; see **Platform docs** below).

**Token lifecycle / 401 recovery.** PATs in `~/.nxd/tokens.json` carry an `expiry`. The nxd CLI itself auto-refreshes the entry when any `nxd` command runs (e.g. `nxd whoami`); the skill's scripts only **read** the file, they do not refresh it. If a per-DP call returns `401 Unauthorized`, fail fast with a message telling the user to run any `nxd` CLI command (the simplest is `nxd whoami`) to refresh, then re-pull the catalogue. Do not silently drop endpoints that 401 — that turns into ghost data. The fix is one line: token file is regenerated from `~/.nxd/tokens.json` after the refresh and passed via `--token-file` to the next call.

### Platform docs (per-mesh)

Docs are served **per-mesh** from the active mesh's app host — there is no single global docs URL. Resolve the base from the mesh config (the `docs_base` / `app_url` that `find_mesh.py` prints), then append a path:

```
<app_url>/docs/#/<path>
```

It is a **docsify** site with hash (`#/`) routing — keep the `#/`, append the path **without** a `.md` extension. If a deep link 404s or shows a blank page, don't guess alternate paths: open the docs home `<app_url>/docs/#/` and navigate its sidebar, use the in-app Learn tab, or re-confirm the host from the mesh config. The doc paths most relevant to **querying / consuming** a Data Product:

| Topic | Path to append to `<app_url>/docs/#/` |
|---|---|
| Consuming another team's DP (REST API contract) | `tutorials/guides/consumer-tutorial` |
| Output ports | `tutorials/guides/02-outputs` |
| Semantic model (attributes / data types) | `tutorials/guides/01-semantic-model` |
| Inputs (request-model field semantics) | `tutorials/guides/04-inputs` |
| Promises & data quality | `tutorials/guides/03-promises` |
| Expectations (access / approval, DQ) | `tutorials/guides/05-expectations` |
| MCP (rpc-outputs / `nxd mcp client`) | `tutorials/guides/07-mcp` |
| CLI setup (mesh / auth) | `tutorials/cli/setup` |
| Create a DP & its infra-profile | `tutorials/cli/create` |

Prefer **showing** over linking — a live `nxd ls …` / REST call against the user's mesh usually beats pointing at a page. Use the links to orient and fill gaps.

---

## Step 2: Pick the Data Product

If the user named one, validate it against the list. Otherwise present the list:

```bash
python3 scripts/list_dps.py --api-url "$API_URL"
```

Outputs one row per DP: `fullName`, `domain`, `version`, `baseUrl`. Use `AskUserQuestion` (single-select) when there are many. When DPs span several `domain` values, first ask the user which **domain** to narrow to (or confirm the one they named), then present only that domain's DPs — don't make them scroll an unscoped list.

The script reads the bearer token from stdin (see **Credentials on the command line** below).

Docs: the consumer REST API contract these calls follow is at `<app_url>/docs/#/tutorials/guides/consumer-tutorial`.

---

## Step 3: Pick the output port

Each DP exposes its output ports at `<baseUrl>/api/v1/outputs`. List them:

```bash
python3 scripts/list_outputs.py --dp <fullName> --api-url "$API_URL"
```

Output per port: `name`, `infra_profile_name`, `infra_service_name`, `model_names`.

Also fetch RPC ports at `<baseUrl>/api/v1/rpc-outputs` — those are MCP/RPC endpoints rather than data ports. Present both lists together, distinguished by kind (`data` vs `rpc`).

If only one port exists, confirm it and proceed. Otherwise prompt the user.

Docs: output-port semantics (`/api/v1/outputs`, `/api/v1/rpc-outputs`) at `<app_url>/docs/#/tutorials/guides/02-outputs`.

---

## Step 4: Show the port's model attributes

Before the user submits a query, surface the column schema of the port's models so they can frame the question against real fields:

```bash
python3 scripts/port_models.py --dp <fullName> --port <port> --api-url "$API_URL"
```

Resolves the port's models in this order: `port.model_names` → `port.promises.model[].model` → DP-level `model_names`. Then fetches `/api/v1/models` and emits each matching model's `name`, `description`, and full `attributes` list (`name`, `data_type`, `description`).

Render the attributes back to the user as a compact table (model → columns + types) and only then ask for the query. For natural-language queries against vector / RPC ports, also call out which column holds the text payload (vector store) or which `request_model` fields the query must populate (RPC).

Docs: to help the user interpret attributes / data types see `<app_url>/docs/#/tutorials/guides/01-semantic-model`; for request-model (input) field semantics see `<app_url>/docs/#/tutorials/guides/04-inputs`; the `port.promises.model[].model` resolution is explained at `<app_url>/docs/#/tutorials/guides/03-promises`.

---

## Step 5: Get port location + credentials

```bash
python3 scripts/connect_port.py --dp <fullName> --port <port> --api-url "$API_URL" --out /tmp/nxd-port.json
```

`connect_port.py` writes to `--out` (never stdout) a JSON document with two keys:

- `location` — the result of `GET /api/v1/outputs/{port}/location`. Carries the data location (host/database/schema for SQL stores, account/container/model_paths for ADLS, bucket/prefix for S3, etc.).
- `connect` — the result of `POST /api/v1/outputs/{port}/connect` with `{"ttl":"<ttl>"}` (default `PT1H`). Returns one of:
  - `status: "connected"` with `leased_credential` (presigned URLs, DB creds, etc.).
  - `status: "approval_pending"` with an approval form — surface the message and `tracking_url` to the user and stop. The access / approval and data-quality expectation model is documented at `<app_url>/docs/#/tutorials/guides/05-expectations`.
  - `status: "unsupported"` — driver does not lease credentials. You then need an **infra-profile** to construct auth out-of-band. **Derive or elicit it — do not assume a local file exists:**
    1. Read the `infra_profile_name` / `infra_service_name` the port declares (from `list_outputs.py` in Step 3).
    2. Resolve the profile against the **active mesh** — `nxd ls infra-profiles` (and `nxd ls infra-services` if available) lists what the mesh actually has; confirm the matching profile/service with the user.
    3. Only if the user genuinely has a working-tree copy from the **nxd-data-product-builder** skill, you may read the infra-profile YAML on disk — but **ask the user to confirm the path first**, don't grep assumed directories. How DPs and their infra-profiles are defined is documented at `<app_url>/docs/#/tutorials/cli/create`.
    4. If neither resolves, ask the user for the infra-profile name (`AskUserQuestion`) rather than guessing.

**Never echo credentials to the chat.** Read `/tmp/nxd-port.json` with `Read`, but only render the location fields back to the user. Pass the file path to the query scripts that need credentials; they read it themselves.

---

## Step 6: Route the query by driver and execute

The infra-service driver (from the port's `infra_service_name` in the infra profile, or from the `leased_credential.details.type_hint` when present) decides which path runs. If **neither** is present, do not assume a driver — resolve the service from the mesh (`nxd ls infra-profiles` / `nxd ls infra-services` against the active mesh) or ask the user which service the port targets (`AskUserQuestion`).

> **Strict mode skips this entire section.** If the user opted into **Strict Mode** (above), do not run any of 6a–6e. Strict mode allows only MCP-mediated access via the mesh MCP gateway + a plan-validation pass. To leave strict mode, the user must explicitly drop the flag.

### 6a. Relational SQL — Snowflake, Postgres, BigQuery, Redshift, Databricks-SQL, DuckDB

The leased credential carries `username`, `password` / `private_key`, plus the location's `host`, `port`, `database`, `schema`. Run SQL via:

```bash
python3 scripts/query_sql.py --creds /tmp/nxd-port.json --sql "<SQL>"
```

If the user asked in natural language, **you (Claude)** generate the SQL from the port's `model_names` plus a `DESCRIBE`-style probe — fetch the model schemas from `<baseUrl>/api/v1/models` and embed them into the SQL you draft. Show the user the SQL you intend to run before running it; only run after they confirm. Cap rows with `LIMIT` and only read the schema/table the location names.

### 6b. File storage — S3, ADLS, MinIO, GCS

The leased credential includes `model_urls` (presigned URLs, per model) — one per output model. The location lists `model_paths` with the on-disk format (`parquet`, `csv`, `json`, …).

```bash
python3 scripts/fetch_file.py --creds /tmp/nxd-port.json --model <model_name> --limit 50
```

`fetch_file.py` downloads the presigned URL into memory, parses the file by format, and writes a small preview JSON to stdout (head + schema). For a real query (filter / aggregate / project), generate SQL and run it via `duckdb` against the downloaded file — `fetch_file.py` supports a `--sql` flag that loads the file as a DuckDB table and executes the SQL.

### 6c. Vector store — pgvector, Pinecone (classic RAG pipeline)

Vector ports run as a small RAG pipeline. The LLM (Claude — this conversation) is the generator; the scripts here are the retriever. The pipeline has five steps. Skip optional steps for cheap one-shot queries; enable them when recall or precision are weak.

**Step 1 — Discover the chunk schema and embedding model.**

Read `/api/v1/info` (DP `description`) and `/api/v1/models` to learn:
- which embedding model produced the index (e.g. `sentence-transformers/all-MiniLM-L6-v2`),
- which column holds the text chunk (default `content`),
- which column holds the vector (default `embedding`),
- what metadata fields ride along (project, status, key, url, dates, …).

Surface the embedding model to the user and confirm before proceeding — querying with a different model from the one used at ingest gives nonsense results.

**Step 2 — Query rewriting (LLM-driven, no script).**

Before embedding, you (Claude) draft 1–3 candidate query strings derived from the user's natural-language question:

- a literal restatement (catches exact terms / IDs),
- a paraphrase that drops chatty wording and surfaces nouns,
- optionally a domain-specific rephrase (e.g. expand acronyms, add synonyms).

Run each candidate through steps 3–5 and fuse results (dedup by primary key, sum RRF scores). For one-shot simple queries skip this — embed the user's question directly.

**Step 3 — Metadata pre-filter (optional).**

If the user's question carries obvious filters (e.g. "in the NXD project", "resolved tickets only", "from last quarter"), apply them as a `WHERE` on the metadata JSON before the similarity search. This is faster and more accurate than letting the vector search return cross-project chunks you then have to discard.

Pass `--filter '<json>'` to `vector_search.py`. The keys/values are whatever metadata fields the port's models actually carry (discovered in Step 4) — the shape below is an **illustrative example**, not a fixed schema:

```json
{"<metadata_field>": "<value>", "<status_field>": ["<value-a>", "<value-b>"]}
```

Equality for scalars, IN-list for arrays. Translates to e.g. `langchain_metadata->>'<field>' = '<value>' AND langchain_metadata->>'<status_field>' IN ('<value-a>','<value-b>')`.

**Step 4 — Retrieve (vector-only or hybrid).**

Compute the query embedding once per candidate query:

```bash
python3 scripts/embed_query.py --model <model-id> --query "<text>" --out /tmp/qvec.json
```

Then retrieve. Two modes:

- **Vector-only** (default) — pgvector kNN with `ORDER BY <vector_col> <-> query::vector LIMIT k`.

  ```bash
  python3 scripts/vector_search.py \
    --backend pgvector --creds /tmp/nxd-port.json \
    --query-vector /tmp/qvec.json --k 5 \
    [--filter '<json>']
  ```

- **Hybrid (RRF fusion of vector + Postgres FTS)** — runs the vector kNN and a `ts_rank` full-text search on the text column in parallel, fuses the two ranked lists with Reciprocal Rank Fusion (k=60). Catches exact-keyword matches the vector misses (IDs, codenames, error strings) without losing semantic recall.

  ```bash
  python3 scripts/vector_search.py \
    --backend pgvector --creds /tmp/nxd-port.json \
    --query-vector /tmp/qvec.json \
    --query-text "<original query text>" \
    --hybrid --candidates 50 --k 5 \
    [--filter '<json>']
  ```

  `--candidates` is the per-list pool size (default 50); each side pulls N candidates, RRF fuses, top-`k` survives. Larger candidates ≈ better recall, more DB work.

  Pinecone hybrid is **not** wired up here — pgvector only.

**Step 5 — Abstain on low confidence (optional).**

Pass `--min-score <f>` to set a floor on the best result's score (RRF score for hybrid, `1/(1+L2)` for vector-only). If no result clears the bar, the script returns `"abstain": true` with empty `rows`. When that fires, **tell the user "no good match in the DP"** rather than hallucinating from weak chunks. The data-quality / expectation model that governs when to trust a port's data is documented at `<app_url>/docs/#/tutorials/guides/05-expectations`.

Reasonable starting thresholds:
- vector-only: `0.45` (≈ L2 distance ≤ 1.2 for normalised embeddings),
- hybrid RRF: `0.02` (one strong-rank hit ≈ `1/(60+1) ≈ 0.016`).

Tune per DP — log a few real queries first.

**Step 6 — Generate the answer (LLM, in the conversation).**

Pass the surviving rows — text chunk + metadata — back into the conversation. You (Claude) synthesise prose for the user's original question. Always **cite** by the metadata that identifies each chunk's source (`key`, `url`, `created`, `assignee`). Cite the chunks you actually used, not the whole top-k. If the script returned `"abstain": true`, say so plainly.

**Step 7 — Agentic loop (optional, LLM-driven, no script).**

If the first retrieval is partial or weak, refine and re-search — up to 3 rounds. Use the existing tools, don't add new ones. Refinement strategies:

- narrow with a metadata filter that the first batch revealed (e.g. user mentioned a project the chunks made explicit),
- broaden by dropping a filter,
- re-rewrite the query using terminology you discovered in the first batch,
- switch from vector-only to `--hybrid` if exact keywords matter,
- raise `--candidates` if RRF fused thinly.

Stop the loop when the score crosses the abstain threshold *and* the chunks plausibly answer the question. Tell the user how many rounds you ran and on what queries — keeps the loop debuggable.

---

**Pipeline summary**

```
user question
  ├─ rewrite (LLM)               → 1..3 candidate queries
  ├─ embed_query.py              → query vector
  ├─ vector_search.py            → kNN  ─┐
  │   --hybrid + --query-text    → FTS  ─┴→ RRF fuse top-k
  │   --filter                   → metadata WHERE
  │   --min-score                → abstain on weak match
  └─ generate (LLM)              → answer + citations
        └─ agentic refine? → re-rewrite → loop (≤3 rounds)
```

`vector_search.py` flags reference: `--filter`, `--hybrid`, `--query-text`, `--candidates`, `--id-col`, `--text-col`, `--vector-col`, `--min-score`. See the script docstring.

### 6d. RPC / MCP port

RPC ports are listed at `/api/v1/rpc-outputs`. Each port declares `functions: [{name, request_model, response_model, description}]`. The MCP client and rpc-outputs contract are documented at `<app_url>/docs/#/tutorials/guides/07-mcp`.

**Consult the LLM.** The user's natural-language question maps onto one of the declared functions:

1. Read `/api/v1/rpc-outputs` and `/api/v1/models` to learn the function names, descriptions, and request/response schemas.
2. Pick the function that matches the user's intent (you, Claude, do this).
3. Construct the request payload conforming to `request_model`.
4. Call the RPC endpoint — for HTTP-style RPC ports, that's `POST <baseUrl>/rpc/<function_name>` with the leased bearer credential; for MCP-stdio ports use `nxd mcp client` (see `nxd mcp --help`) and invoke the function over MCP.
5. Show the response to the user; for natural-language answers, synthesise from the response payload.

```bash
python3 scripts/rpc_call.py --dp <fullName> --port <port> --function <fn> --args '<json>' --api-url "$API_URL"
```

`rpc_call.py` reads the token from stdin and writes the response to stdout (or to `--out` if `--out` is supplied — preferred for large payloads).

### 6e. External API ports — `driver: api`

The location is a URL; the leased credential is whatever the upstream API needs (bearer, basic, key). Build the HTTP call from the model schema, run it via `curl` or `python -m requests`.

---

## Credentials on the command line

**Never put a bearer token or password on a command line.** The scripts read secrets from one of:

- `stdin` — pipe the token in: `echo "$TOK" | python3 scripts/list_dps.py …`
- `--token-file <path>` — a file containing the token (write to a `/tmp/` file with `chmod 600`).
- A JSON credentials file (`--creds /tmp/nxd-port.json`) — the leased credential blob produced by `connect_port.py`.

The skill itself never prints tokens, presigned URLs, or DB passwords back to the chat. When showing the user what was leased, show the *fields available* (e.g. `presigned_url`, `database`, `schema`) — not the values.

---

## Scripts

The skill ships small Python entrypoints under `scripts/`. Install dependencies into a throwaway venv:

```bash
python3 -m venv /tmp/nxd-data-product-query/venv
/tmp/nxd-data-product-query/venv/bin/pip install -r scripts/requirements.txt
```

| Script | Purpose |
|---|---|
| `find_mesh.py` | Discover the active mesh URL and bearer token from `~/.nxd/` |
| `list_dps.py` | `GET /api/v1/data-products` — list deployed DPs on the mesh |
| `list_outputs.py` | `GET <dp>/api/v1/outputs` and `/api/v1/rpc-outputs` — list ports |
| `port_models.py` | Resolve a port's models and emit each model's attributes (name, type, description) |
| `connect_port.py` | `GET /location` + `POST /connect` — fetch port location + leased credential |
| `query_sql.py` | Run a SQL query against the leased database credential |
| `fetch_file.py` | Download a leased presigned URL, preview / SQL-query the file with DuckDB |
| `embed_query.py` | Compute an embedding for a query string using a named model |
| `vector_search.py` | Vector similarity search against pgvector / Pinecone |
| `rpc_call.py` | Invoke a function on an RPC output port |
| `mcp_http.py` | (Strict mode) Minimal MCP Streamable-HTTP client used by the strict-mode scripts — handles `initialize`, session id, `tools/list`, `tools/call` |
| `mcp_gateway.py` | (Strict mode) Wraps `nxd mcp health --format json` for endpoint discovery; calls `tools/list` per healthy DP MCP endpoint to capture the tool catalogue. **Re-run every query** — the DP set + tools are not stable |
| `semantic_relations.py` | (Strict mode) For each gateway DP whose tools include a name matching `^semantic[_-]?models?$` (regex overridable), calls that tool and merges the response into a single relations bundle. **Re-run every query** |
| `plan_validator.py` | (Strict mode) Pure local plan validator. Checks the plan against the gateway catalogue + relations bundle. Emits `{passed, checks, failures}`. Network-free — caller must keep the catalogue + relations fresh |

Each script writes secrets only to `--out` files (never stdout) and reads tokens via `--token-file` or stdin.

---

## Gotchas

- **Token expiry** — `tokens.json` carries an `expiry`. If a 401 comes back, ask the user to re-run `nxd login` (or the **nxd-setup** skill) and retry. Per-mesh auth/PAT setup is documented at `<app_url>/docs/#/tutorials/cli/setup`.
- **`connect` returns `unsupported`** — derive the infra-profile from the active mesh (`nxd ls infra-profiles`) or ask the user; only read an on-disk infra-profile YAML if the user confirms they have a working-tree copy (e.g. from `nxd-data-product-builder`) and confirms the path. Do not grep assumed directories. See `<app_url>/docs/#/tutorials/cli/create`.
- **`connect` returns `approval_pending`** — stop and surface the `message` / `tracking_url` to the user. Do not poll.
- **Long-lived presigned URLs** — every `connect` call returns fresh credentials with a fixed TTL. Cache the response in `/tmp/nxd-port.json` for the session; re-request if the TTL passes.
- **Vector store embedding model mismatch** — querying with a different embedding model from the one the DP used to index gives nonsense results. Always confirm the model from the DP's `description` / `/v1/info` before computing the query vector.
- **MCP vs HTTP RPC** — the same DP may expose its RPC port via both. Prefer HTTP when running one-shot; use `nxd mcp client` only when the user explicitly wants interactive MCP.
- **Strict mode validation failures are terminal** — when `plan_validator.py` returns `passed=false`, do **not** fall back to default routing in the same run. Return the failure to the user and stop. Falling back silently would defeat the rule. If the user wants the fallback, they must explicitly drop strict mode.
- **Strict mode + unknown relationships** — if a join the question seems to need is not present in any `semantic_model` MCP response, the right answer is "I can't do this in strict mode" — not "I'll guess from column names". Add the missing relationship to the source DP's `semantic_model` and redeploy, or ask the user to drop strict mode.
