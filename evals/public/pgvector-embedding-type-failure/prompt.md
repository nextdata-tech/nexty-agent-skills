# Scenario: pgvector Embedding-Column Type Failure

The eval runner should provide a vector Data Product whose transform fails (or
whose write is refused) at output time. The semantic model declares the
embedding attribute as `string()`, so the pgvector driver provisioned a `TEXT`
column and langchain/pgvector refuses to write vectors into it. The platform
error surfaces at write time, far from the spec — e.g. `Embedding column is not
type Vector`.

Task for the agent:

Diagnose the failure and propose the smallest safe fix.

Required artifacts from eval runner:

- `nxd describe data-product` / status reason output showing the write-time error.
- `nxd logs` output including the `Embedding column is not type Vector` (or equivalent) message.
- Data-product source directory with `models.py`/`spec.py` declaring the embedding attribute as `string()`.

Success checks:

- The agent reads the status reason / logs before guessing, and notices the error is at the WRITE stage, not a generic transform crash.
- The agent identifies the root cause as the embedding attribute being declared `string()` instead of `vector_embeddings(<dim>)` — i.e. the table was provisioned as TEXT, not vector.
- The agent fixes the semantic model to `vector_embeddings(<dim>)` with the dimension the embedding model emits (e.g. 384 for `all-MiniLM-L6-v2`, 1536 for OpenAI `text-embedding-3-small`).
- The agent states that the table must be re-provisioned (re-launch) for the column type to change, and does not merely re-run the transform against the wrong column.
- The agent does NOT misattribute the failure to credentials, memory, or API parsing.
