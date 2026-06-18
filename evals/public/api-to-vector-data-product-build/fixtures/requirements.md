# Requirements Brief: Issue-Tracker Semantic Search Index

## 1. Background

Our support and engineering teams want to run semantic search over our
issue tracker so they can find related tickets, surface duplicate reports,
and feed a retrieval step for an assistant. The raw tickets live behind a
hosted issue-tracking SaaS REST API. We want a data product that pulls
tickets on a regular cadence, flattens their nested content into clean
text records, embeds that text, and lands the embeddings in a vector store
that downstream search and RAG services can query.

Build this as a Nextdata OS Python data product. The sections below state
what the product must do; choose the implementation details (file layout,
DSL wiring, helper structure) yourself.

## 2. Product identity

- Data product name: `issue-tracker-search-index`
- Domain: `Support`
- Purpose: maintain an always-fresh vector index of issue-tracker tickets
  for semantic search and retrieval.

## 3. Source: Issue-Tracker REST API

The source is a generic hosted issue tracker exposed over a REST API.

- Base URL: `https://api.example.com/v2`
- Tickets endpoint: `GET https://api.example.com/v2/issues`
- Auth: a bearer token supplied at runtime through the platform's secret
  /credential mechanism. The token must NOT appear in any source file,
  config literal, or committed text. Assume the runtime provides it.

### 3.1 Pagination (required)

The `/issues` endpoint is **cursor-paginated**. Each response body looks
like:

```json
{
  "data": [ { ...issue... }, ... ],
  "next_cursor": "eyJvZmZzZXQiOjUwfQ==",
  "page_size": 50
}
```

- Request with `?page_size=50` and, on subsequent pages, `?cursor=<next_cursor>`.
- `next_cursor` is `null` on the final page.
- The product MUST walk every page until `next_cursor` is null. Do not stop
  after the first page. Use page size 50.

### 3.2 Project and date filters (required)

The pull is scoped, not a full-history dump. Apply these query filters on
the `/issues` request:

- `project=ENG` — only pull tickets from the project whose key is `ENG`.
- `updated_after=2024-01-01` — only pull tickets updated on or after this
  date (ISO `YYYY-MM-DD`).

Both filters must be applied at the API request level (server-side), not
by pulling everything and discarding rows afterward.

### 3.3 Issue shape and nested document parsing (required)

A single issue object looks like this:

```json
{
  "id": "ENG-1042",
  "project": "ENG",
  "title": "Login page returns 500 under load",
  "body": "Users report intermittent 500s when signing in during peak hours.",
  "status": "open",
  "priority": "high",
  "updated_at": "2024-03-11T09:22:00Z",
  "labels": ["auth", "performance"],
  "comments": [
    {
      "author": "ada",
      "created_at": "2024-03-11T10:01:00Z",
      "text": "Reproduced on staging with 200 concurrent logins."
    },
    {
      "author": "lin",
      "created_at": "2024-03-11T11:30:00Z",
      "text": "Looks like the session store is the bottleneck."
    }
  ]
}
```

The issue is a **nested document**. The product must flatten each issue
into the text + metadata that will be embedded:

- Concatenate the issue `title` and `body`, then append every comment's
  `text` (in order) into a single document text field for that issue.
- Carry these flattened metadata fields alongside the text on each record:
  `id`, `project`, `status`, `priority`, `updated_at`, and `labels`
  (joined into a single string).
- `comments` may be an empty list; handle that without error.

### 3.4 Custom input expectation (required)

Tickets are the join key for everything downstream, so a missing or null
`id` is unacceptable. Wire a custom input expectation that fails the run
if any pulled issue has a null, empty, or missing `id`. State this as an
explicit data-quality check on the input, not just defensive code buried
in the parser.

## 4. Transform: chunking and embedding

After flattening, each issue's document text must be split into chunks and
embedded.

- **Chunking**: split the flattened document text into chunks of **512
  tokens** with an **overlap of 64 tokens**. One issue may produce several
  chunk records.
- **Embedding model**: `all-MiniLM-L6-v2`, which produces **384-dimensional**
  vectors. Use this exact model; the vector dimension downstream is 384.
- Each output record is one chunk: its embedding vector, the chunk text,
  the parent issue `id`, a chunk index, and the carried metadata fields
  from section 3.3.

## 5. Output: vector store

The output is a **vector store** that downstream semantic-search and RAG
services query by vector similarity.

- The output port writes embeddings (and the per-chunk text + metadata)
  into a **pgvector**-backed vector store.
- The vector store is configured to ingest embeddings of dimension 384,
  matching the embedding model above.
- **Do NOT attach a tabular/semantic schema to the vector output port.**
  The vector store manages its own embedding layout; forcing a column
  schema onto it is wrong for this output and must not be done. (A schema
  on the *input* side, where it models the flattened records, is fine — the
  prohibition is specifically about the vector output.)

## 6. Service names (use verbatim)

The infra profile for this product exposes two distinct services. Use
these exact service names when wiring the input and the output — do not
fall back to demo or placeholder service names:

- Input service (the issue-tracker API connection): `issue-tracker-api`
- Output service (the pgvector store): `pgvector-search-store`

## 7. Schedule

The index must stay fresh. Run the pull-flatten-embed-write pipeline on a
**daily schedule at 02:00 UTC** (cron `0 2 * * *`).

## 8. Local validation and handover

Before any launch:

- Write a **local validation / smoke-test script** that can be run
  offline: it should exercise the pagination walk and the nested-document
  flattening against a small sample payload (you may inline a tiny fake
  response), and assert the custom `id` expectation logic, without calling
  the live API or the live vector store.
- Run the platform's static validation (`nxd validate`) on the finished
  product.
- Produce a short handover note stating whether `nxd validate` was run and
  exactly what happened (passed, or failed with which error and how it was
  resolved). Do not claim it passed if it was not actually run.

## 9. Out of scope / do not do

- Do not embed real credentials, tokens, or hostnames other than the
  `example.com` placeholders above.
- Do not launch to a real customer mesh unless a sandbox mesh is provided.
- Do not add a schema to the vector output port (see section 5).
