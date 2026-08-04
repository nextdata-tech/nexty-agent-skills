# Vector store RAG pipeline (pgvector, Pinecone)

## Contents

- [Step 1 — Discover schema + embedding model](#step-1--discover-the-chunk-schema-and-embedding-model)
- [Step 2 — Query rewriting](#step-2--query-rewriting-llm-driven-no-script)
- [Step 3 — Metadata pre-filter](#step-3--metadata-pre-filter-optional)
- [Step 4 — Retrieve (vector-only or hybrid)](#step-4--retrieve-vector-only-or-hybrid)
- [Step 5 — Abstain on low confidence](#step-5--abstain-on-low-confidence-optional)
- [Step 6 — Generate the answer](#step-6--generate-the-answer-llm-in-the-conversation)
- [Step 7 — Agentic loop](#step-7--agentic-loop-optional-llm-driven-no-script)
- [Pipeline summary](#pipeline-summary)

This is the §6c expansion from [SKILL.md](../SKILL.md). Vector ports run as a
small RAG pipeline: the LLM (Claude — the conversation) is the generator; the
scripts (`embed_query.py`, `vector_search.py`) are the retriever. Skip optional
steps for cheap one-shot queries; enable them when recall or precision are weak.
Credentials come from the leased `<port_credentials_file>` (Step 5 of SKILL.md —
the gateway has no lease tool, so this path stays on REST `connect_port.py`).

**Step 1 — Discover the chunk schema and embedding model.**

Read the models via `gateway_tools.py details --dp <dp> --models`. Discovery goes
through the MCP gateway, not REST — SKILL.md's gateway-first rule is the contract,
and REST `/api/v1/models` can answer from a different or staler schema. Learn:
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

Pass `--filter '<json>'` to `vector_search.py`. The keys/values are whatever metadata fields the port's models actually carry (discovered in Step 1) — the shape below is an **illustrative example**, not a fixed schema:

```json
{"<metadata_field>": "<value>", "<status_field>": ["<value-a>", "<value-b>"]}
```

Equality for scalars, IN-list for arrays. Translates to e.g. `langchain_metadata->>'<field>' = '<value>' AND langchain_metadata->>'<status_field>' IN ('<value-a>','<value-b>')`.

**Step 4 — Retrieve (vector-only or hybrid).**

Compute the query embedding once per candidate query:

```bash
python3 scripts/embed_query.py --model <model-id> --query "<text>" --out <query_vector_file>
```

Then retrieve. Two modes:

- **Vector-only** (default) — pgvector kNN with `ORDER BY <vector_col> <-> query::vector LIMIT k`.

  ```bash
  python3 scripts/vector_search.py \
    --backend pgvector --creds <port_credentials_file> \
    --query-vector <query_vector_file> --k 5 \
    [--filter '<json>']
  ```

- **Hybrid (RRF fusion of vector + Postgres FTS)** — runs the vector kNN and a `ts_rank` full-text search on the text column in parallel, fuses the two ranked lists with Reciprocal Rank Fusion (k=60). Catches exact-keyword matches the vector misses (IDs, codenames, error strings) without losing semantic recall.

  ```bash
  python3 scripts/vector_search.py \
    --backend pgvector --creds <port_credentials_file> \
    --query-vector <query_vector_file> \
    --query-text "<original query text>" \
    --hybrid --candidates 50 --k 5 \
    [--filter '<json>']
  ```

  `--candidates` is the per-list pool size (default 50); each side pulls N candidates, RRF fuses, top-`k` survives. Larger candidates ≈ better recall, more DB work.

  Pinecone hybrid is **not** wired up here — pgvector only.

**Step 5 — Abstain on low confidence (optional).**

Pass `--min-score <f>` to set a floor on the best result's score (RRF score for hybrid, `1/(1+L2)` for vector-only). If no result clears the bar, the script returns `"abstain": true` with empty `rows`. When that fires, **tell the user "no good match in the data product"** rather than hallucinating from weak chunks. The data-quality / expectation model that governs when to trust a port's data is documented at `<app_url>/docs/#/tutorials/guides/05-expectations`.

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

## Pipeline summary

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
