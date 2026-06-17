# Scenario: Duplicate Rows on Every Re-run

The eval runner should provide a Data Product whose run status is green but whose
output row count multiplies on every scheduled run. The transform generates chunk
ids with random UUIDs, so each run inserts fresh rows instead of upserting, and
there is no unique index for the upsert to conflict on.

Task for the agent:

Diagnose why the row count grows and propose the smallest safe fix.

Required artifacts from eval runner:

- Output port row counts from two consecutive runs (growing).
- Data-product source directory with the transform using random UUIDs for chunk ids.

Success checks:

- The agent recognizes that a green run with a growing row count is an idempotency problem, not a failure to investigate via crash logs.
- The agent identifies the random-UUID id generation as the cause of non-idempotent inserts.
- The agent proposes deterministic ids (e.g. `uuid.uuid5(...)` keyed on source + record key + chunk index) so re-runs upsert instead of insert.
- The agent notes that langchain/pgvector upserts need a unique index (e.g. `CREATE UNIQUE INDEX IF NOT EXISTS ... (langchain_id)`) for `ON CONFLICT` to work.
- The agent does NOT propose deleting all rows before each run as the only fix, nor blame the schedule itself.
