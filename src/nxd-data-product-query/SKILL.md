---
name: nxd-data-product-query
description: Query a Nextdata OS Data Product through its REST API. Discovers the active mesh from the user's local nxd settings, lists Data Products and their output ports, fetches each port's location and a leased credential from the Data Product's REST API, then runs the user's query against the port using credentials returned by the platform. Routes by service type — SQL for relational stores (Snowflake, Postgres, BigQuery, Redshift, Databricks, pgvector metadata), presigned-URL fetch for file storage (S3, ADLS), vector similarity for vector stores (pgvector, Pinecone), and MCP/RPC calls for RPC ports — and consults the LLM (Claude) to translate natural-language questions into the right query for vector stores and MCP endpoints. Use when the user asks to "query a data product", "read from an output port", "search jira-embeddings", "fetch the latest rows from a named DP", or similar.
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

For **vector stores** and **MCP / RPC ports**, this skill consults the LLM (Claude — the conversation itself) to turn the user's natural-language question into a concrete query (vector similarity expression, MCP call payload) before executing.

This skill is read-only. It never writes to a data product's output store.

---

## Inputs the user can supply up-front

The user may pass any of these in the request — collect the rest interactively:

- **Data Product** — `fullName` (e.g. `jira-embeddings-demo`). If missing, prompt with the list returned by `/api/v1/data-products`.
- **Output port** — port `name` (e.g. `pgvector`, `adls`, `snowflake-out`). If missing, prompt with the list returned by `/api/v1/outputs` on that DP.
- **Query** — natural-language question, or a SQL string, or a vector-search description, or an MCP function + args. If missing, ask.

---

## Step 1: Locate mesh + auth

Read the user's local nxd settings. The mesh URL is needed to list Data Products; the bearer token is needed to call the per-DP API.

```bash
python3 scripts/find_mesh.py
```

`find_mesh.py` returns JSON `{ "api_url": "...", "token": "..." }`:

- Reads `~/.nxd/meshes.json` first (the registry the nxd-setup skill maintains).
- Falls back to `~/.nxd/config.yaml` — top-level `url:` and entries under `meshes:`.
- If multiple meshes are present, prints them and exits non-zero with a list. **Never guess the mesh** — do not infer it from the Data Product name or from where a DP "likely" lives. Resolve it two ways only: (1) if the config marks one mesh active (`config.yaml (active)`), use that one and re-run with `--mesh <name>`; (2) otherwise ask the user which one (use `AskUserQuestion`) and re-run with `--mesh <name>`.
- Token comes from the registry entry first; if absent, reads `~/.nxd/tokens.json` (the file `nxd login` writes). Tokens there are keyed by the OAuth auth domain — `find_mesh.py` resolves the right entry by matching the api host.

If neither file is present or no usable token is found, tell the user to run the **nxd-setup** skill first.

---

## Step 2: Pick the Data Product

If the user named one, validate it against the list. Otherwise present the list:

```bash
python3 scripts/list_dps.py --api-url "$API_URL"
```

Outputs one row per DP: `fullName`, `domain`, `version`, `baseUrl`. Use `AskUserQuestion` (single-select) when there are many.

The script reads the bearer token from stdin (see **Credentials on the command line** below).

---

## Step 3: Pick the output port

Each DP exposes its output ports at `<baseUrl>/api/v1/outputs`. List them:

```bash
python3 scripts/list_outputs.py --dp <fullName> --api-url "$API_URL"
```

Output per port: `name`, `infra_profile_name`, `infra_service_name`, `model_names`.

Also fetch RPC ports at `<baseUrl>/api/v1/rpc-outputs` — those are MCP/RPC endpoints rather than data ports. Present both lists together, distinguished by kind (`data` vs `rpc`).

If only one port exists, confirm it and proceed. Otherwise prompt the user.

---

## Step 4: Show the port's model attributes

Before the user submits a query, surface the column schema of the port's models so they can frame the question against real fields:

```bash
python3 scripts/port_models.py --dp <fullName> --port <port> --api-url "$API_URL"
```

Resolves the port's models in this order: `port.model_names` → `port.promises.model[].model` → DP-level `model_names`. Then fetches `/api/v1/models` and emits each matching model's `name`, `description`, and full `attributes` list (`name`, `data_type`, `description`).

Render the attributes back to the user as a compact table (model → columns + types) and only then ask for the query. For natural-language queries against vector / RPC ports, also call out which column holds the text payload (vector store) or which `request_model` fields the query must populate (RPC).

---

## Step 5: Get port location + credentials

```bash
python3 scripts/connect_port.py --dp <fullName> --port <port> --api-url "$API_URL" --out /tmp/nxd-port.json
```

`connect_port.py` writes to `--out` (never stdout) a JSON document with two keys:

- `location` — the result of `GET /api/v1/outputs/{port}/location`. Carries the data location (host/database/schema for SQL stores, account/container/model_paths for ADLS, bucket/prefix for S3, etc.).
- `connect` — the result of `POST /api/v1/outputs/{port}/connect` with `{"ttl":"<ttl>"}` (default `PT1H`). Returns one of:
  - `status: "connected"` with `leased_credential` (presigned URLs, DB creds, etc.).
  - `status: "approval_pending"` with an approval form — surface the message and `tracking_url` to the user and stop.
  - `status: "unsupported"` — driver does not lease credentials. Fall back to using the **infra-profile service** named in the port (`infra_profile_name` / `infra_service_name`) to construct auth out-of-band: read the infra-profile YAML the user has on disk (search `infra-profiles/`, `./.nxd/skills/nxd-data-product-builder/`, `~/.nxd/skills/nxd-data-product-builder/`) and pull the matching service's attributes. Ask the user to confirm the file before reading credentials from it.

**Never echo credentials to the chat.** Read `/tmp/nxd-port.json` with `Read`, but only render the location fields back to the user. Pass the file path to the query scripts that need credentials; they read it themselves.

---

## Step 6: Route the query by driver and execute

The infra-service driver (from the port's `infra_service_name` in the infra profile, or from the `leased_credential.details.type_hint` when present) decides which path runs.

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

Pass `--filter '<json>'` to `vector_search.py`:

```json
{"project": "NXD", "status": ["Done", "Closed"]}
```

Equality for scalars, IN-list for arrays. Translates to `langchain_metadata->>'project' = 'NXD' AND langchain_metadata->>'status' IN ('Done','Closed')`.

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

Pass `--min-score <f>` to set a floor on the best result's score (RRF score for hybrid, `1/(1+L2)` for vector-only). If no result clears the bar, the script returns `"abstain": true` with empty `rows`. When that fires, **tell the user "no good match in the DP"** rather than hallucinating from weak chunks.

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

RPC ports are listed at `/api/v1/rpc-outputs`. Each port declares `functions: [{name, request_model, response_model, description}]`.

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

Each script writes secrets only to `--out` files (never stdout) and reads tokens via `--token-file` or stdin.

---

## Gotchas

- **Token expiry** — `tokens.json` carries an `expiry`. If a 401 comes back, ask the user to re-run `nxd login` (or the **nxd-setup** skill) and retry.
- **`connect` returns `unsupported`** — fall back to the infra profile file on disk for credentials, as in `nxd-data-product-builder`. Ask the user to confirm the file path before reading.
- **`connect` returns `approval_pending`** — stop and surface the `message` / `tracking_url` to the user. Do not poll.
- **Long-lived presigned URLs** — every `connect` call returns fresh credentials with a fixed TTL. Cache the response in `/tmp/nxd-port.json` for the session; re-request if the TTL passes.
- **Vector store embedding model mismatch** — querying with a different embedding model from the one the DP used to index gives nonsense results. Always confirm the model from the DP's `description` / `/v1/info` before computing the query vector.
- **MCP vs HTTP RPC** — the same DP may expose its RPC port via both. Prefer HTTP when running one-shot; use `nxd mcp client` only when the user explicitly wants interactive MCP.
