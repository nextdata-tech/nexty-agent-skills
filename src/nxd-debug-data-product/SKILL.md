---
name: nxd-debug-data-product
description: Debug failed or unhealthy Nextdata OS data products. Use when diagnosing nxd validate, launch, deploy, startup timeout, dependency install, compute status, logs, init container, MCP server, semantic-layer / rpc-MCP DP, policy, contract, output write, or transform runtime failures and choosing the smallest safe fix.
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
  version: 0.34.0
---

# NXD Data Product Debugging

Diagnose from evidence first, then patch the smallest source, config, dependency, resource, or contract issue.

## Setup

- Confirm `nxd-setup-cli` has selected the mesh and produced `<session_config>`.
- Resolve `<app_url>` from the active mesh registry and use docs paths:
  - `<app_url>/docs/#/dp_development/debugging`
  - `<app_url>/docs/#/tutorials/cli/create`
  - `<app_url>/docs/#/tutorials/guides/03-promises`
  - `<app_url>/docs/#/tutorials/guides/05-expectations`

## Loop

The order matters. Run it as a loop, not a single pass:

1. **Gather evidence** (Evidence First) — lowest-risk reads, no changes.
2. **Form a hypothesis** — name the single most likely cause from the evidence.
   The first error is often not the root cause; later errors are usually
   fallout from the first. Read `nxd logs` from the FIRST error.
3. **Probe to discriminate** — when two causes explain the same symptom, run the
   one cheap read that tells them apart *before* touching code (see the
   discriminator table in
   [nxd-build-data-product/reference/troubleshooting.md](../nxd-build-data-product/reference/troubleshooting.md)).
4. **Patch the smallest surface** that the confirmed cause points to.
5. **Verify** — re-run the check that failed, then re-read status/logs.
6. If not fixed, return to step 1 with the new evidence.

The symptom→cause→fix catalog backing steps 2–4 lives in
[troubleshooting.md](../nxd-build-data-product/reference/troubleshooting.md)
(deployed-runtime failures) and
[common-pitfalls.md](../nxd-build-data-product/reference/common-pitfalls.md)
(authoring-time failures). Consult them rather than re-deriving causes.

## Evidence First

Run the lowest-risk reads before guessing:

```bash
nxd --config <session_config> describe data-product <dp-name> --compute-status
nxd --config <session_config> logs <dp-name> --debug-logs
nxd --config <session_config> logs <dp-name> --init --debug-logs
```

If the failure involves MCP/RPC output code:

```bash
nxd --config <session_config> logs <dp-name> --mcp --debug-logs
```

For local source and service preflight:

```bash
nxd --config <session_config> whoami
nxd validate --config <session_config> <data_product_directory> --debug
echo "nxd validate exit code: $?"
nxd --config <session_config> verify dp --dir <data_product_directory> --json
```

Read the runtime/init logs (`nxd logs`) before concluding — the platform writes
the failure cause there. Note that `BatchLogProcessor.ExportError ... connection
refused` lines are the telemetry exporter, **not** the data-product failure;
ignore them and look for the actual traceback or `nxd describe` status reason.

## Failure Triage

- Config/spec parse error: inspect `spec.py`, model imports, service URLs, infra profile names, and transform parameter names.
- Dependency install or init failure: inspect init logs, `requirements.txt`, `pyproject.toml`, `.nxdignore`, package indexes, and flat-layout packaging. `ModuleNotFoundError: No module named 'nxd.data_product'` means `requirements.txt` is missing the SDK — both `nxd_core` and `nxd_data_product` are always required.
- Stuck in `PROVISIONING`: the environment is still installing — a dependency install is failing (bad package name, unavailable version, unreachable index). Read init logs. `PROVISIONING` is a state, not yet an error.
- Startup timeout: inspect init logs and runtime logs before assuming timeout. OOM can appear as startup timeout. Discriminate via the status reason / exit 137, not by guessing.
- Transform runtime error: reproduce with the local transform runner, then fix parsing, type conversion, chunking, output writes, or API paging.
- Output write failure: check driver context, service credentials, table/path/index names, schema settings, and promise code. For pgvector: `Embedding column is not type Vector` means the embedding attribute was declared `string()` instead of `vector_embeddings(<dim>)`; a dimension-mismatch error means the declared dimension ≠ the model output (see troubleshooting.md §4). **The pgvector driver provisions the column type FROM the model, so fixing the spec is NOT enough on its own: the existing table already has the wrong (`TEXT`) column. The fix must RE-PROVISION the table — re-launch the data product (or drop the table) so the column is recreated as `vector` — not merely re-run the transform against the wrong column.** The same applies to a `vector_embeddings(N)` dimension change.
- Row count multiplies on every (green) run = an **idempotency** bug, not a crash — do not hunt failure logs. Cause: chunk ids generated with random UUIDs, so every run INSERTs fresh rows. Fix: deterministic ids (`uuid.uuid5(namespace, f"<source>:{record_key}:{chunk_index}")`) so reruns upsert instead of insert. **langchain/pgvector upserts via `ON CONFLICT` on `langchain_id`, which only works if the table has a unique index — add `CREATE UNIQUE INDEX IF NOT EXISTS ... ON <table> (langchain_id)` at transform start.** Do NOT "fix" it by deleting all rows each run (`write_mode("overwrite")` / truncate-then-write) unless that is an explicitly chosen strategy, and do not blame the schedule.
- Policy or contract failure: switch to `nxd-fix-policy-failures`.
- **Semantic-layer / rpc-MCP DP won't serve** (the `nxd.experimental.semantic` kind exposing `list_models`/`describe_model`/`run_semantic_query`). Evidence: `nxd describe data-product <dp>` for the state + reason, `nxd logs <dp> --debug-logs` (and `--mcp --debug-logs` for the tool server), `nxd mcp health` for discovery state (`derived_state` + `tool_count`; on a single-/default-mesh config run it WITHOUT `--mesh`, pass `--mesh <name>` only when your config defines named meshes). These are **authoring** traps — diagnose the symptom here, then **fix in the DP source via the `nxd-build-semantic-data-product` skill** (which carries the full recipe). Symptom → diagnosis:
  - **Status reason `Field <X> not found in the model` on the promised model** → the base table is seeded by the transform, but the kernel runs promise verification **before** the transform on this output path, so the table doesn't exist yet. (Fix: `nxd-build-semantic-data-product` Step 4 — "Base tables must exist before promise verification": use the facade-over-pre-existing-tables pattern, or accept that a pure self-seed won't pass in a single launch.)
  - **Pod startup `ModuleNotFoundError: No module named 'registry'` (or `tools`)** → the rpc-output `code(fn)` path ships only the extracted tool scripts, not the sibling modules they import; a `.transform(...)` is what triggers the `**/*.py` glob that bundles the siblings. (Fix: Step 4 — declare the mandatory `.transform(...)`; keep all modules flat at the DP root, never a subdir package.)
  - **DP cycles running↔failed, reason `Timeout waiting for execution to start`** → the compute step exceeded its startup budget (slow image / cold start, or a heavy re-seeding transform). (Fix: Step 4 — keep the transform lean / prefer the facade pattern so provisioning is a view DDL rather than a re-seed.)
  - **`nxd mcp health` `Broken`/`tool_count: 0`, or a call returns `Unknown tool: list_models`** → the rpc server registered zero tools. Inspect the rpc/mcp logs for a tool-registration `NameError`/import error at load (e.g. an extracted tool referencing a module-level constant), and confirm the served wheel set is current and matched (`core` + `drivers` + `data_product` same version). (Fix: Step 3 — author module-level functions in a flat `tools.py`; reuse `build_semantic_tools(...)` only for the request/response schemas.)
  - **`run_semantic_query` errors `'Context' object has no attribute 'connector_params'` / `Context cannot be converted to ContextData`** → the tool's `snowflake` param is untyped, so the rpc runtime injects a raw `Context` instead of the driver handle. (Fix: Step 3 — type the param with the driver class, `snowflake: Snowflake`, module-level import. Per-DP author code, not a library bump.)
  - **`nxd validate` errors `Facade view output(s) cannot be combined with .transform()`** → an rpc DP can't use a facade `as_view` output alongside the required `.transform(...)`. (Fix: Step 4 — provision the view inside the mandatory transform via `native_semantic_view_ddl` / `plain_view_ddl`, not a facade `as_view` output.)
  - **Provision/transform error creating a view that references another DP's table** → the view DDL must reference only this DP's own tables; cross-DP joins resolve at query time. (Fix: Step 4 — provision a view over this DP's own tables only.)
  - **Query compiles + executes but `row_count: 0`** → the base table was never populated (the transform's self-seed didn't run, or a clean re-provision wiped it). (Fix: Step 4 — verify the seed actually populates the table; the facade-over-pre-existing-tables pattern avoids the self-seed timing entirely.)
- Removed semantic model: restore the deployed model name or launch a versioned product.
- `nxd validate` returns to prompt with little/no output: first check `whoami`.
  If auth says `Not logged in`, validation is NOT RUN even if exit code is 0.
  If auth is valid, rerun without `--debug` and capture the exit code. Treat
  `Service <name> not found` as an infra-profile/service mismatch, not a
  transform bug — list the profile's real services and match the name exactly
  (see troubleshooting.md §7 for the verify/list commands).

## Patch And Verify

**Before handing back a fix, state its operational consequence — a spec edit alone is often not the whole fix:**

- **pgvector embedding type/dimension change** (`string()` → `vector_embeddings(<dim>)`, or a dimension change): the driver provisions the column type FROM the model at launch, so the EXISTING table still has the wrong (`TEXT`/old-width) column. The fix is incomplete unless you tell the user the table must be **re-provisioned** — re-launch the data product (or drop the table) so the column is recreated. Re-running the transform alone writes against the wrong column and fails again.
- **Duplicate/growing rows on a green run** (idempotency): deterministic ids are only half the fix. langchain/pgvector upserts via `ON CONFLICT` on `langchain_id`, which needs a **unique index** — state that `CREATE UNIQUE INDEX IF NOT EXISTS ... ON <table> (langchain_id)` must exist (create it at transform start). Do not propose delete-all-rows / `write_mode("overwrite")` as the fix and do not blame the schedule.

1. Patch the smallest source/config surface that matches the evidence.
2. Re-run local smoke tests or contract checks.
3. Re-run `nxd validate`.
4. If the product is already deployed and only failed/skipped models need another run:

```bash
nxd --config <session_config> run <dp-name> --retry --follow
```

5. If source or deployment config changed, tell the user the launch command:

```bash
nxd launch --dir <data_product_directory> --config <session_config>
```

6. Re-read `describe data-product --compute-status` and relevant logs.

## Guardrails

- Do not jump from a generic startup timeout to a code patch without reading init and debug logs.
- Do not invent `nxd retry` or `nxd reset`; use `nxd run --retry`.
- Do not hide failed validation behind a handover checklist.
- Do not mark `nxd validate` PASS unless `whoami` confirmed auth, validate exited 0, and no validation error/traceback was printed.
- Do not print secrets from logs, profiles, or leased credentials.
- A spec edit that changes a PROVISIONED column type or width is INCOMPLETE on its own. Do not present a pgvector `string()`→`vector_embeddings(<dim>)` (or dimension) fix as done without stating that the existing table must be **re-provisioned / re-launched** (or dropped) for the new column type to take effect — re-running the transform alone hits the same stale column.
- Do not present an idempotency / duplicate-rows fix (deterministic ids) as done without stating that langchain/pgvector `ON CONFLICT` upserts require a **unique index on `langchain_id`** (`CREATE UNIQUE INDEX IF NOT EXISTS ...`). Deterministic ids without the unique index still insert duplicates.
