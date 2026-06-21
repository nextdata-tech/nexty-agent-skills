---
name: nxd-debugging-data-products
description: Debug failed or unhealthy Nextdata OS data products. Use when diagnosing nxd validate, launch, deploy, startup timeout, dependency install, compute status, logs, init container, MCP server, policy, contract, output write, or transform runtime failures and choosing the smallest safe fix.
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
  version: 0.2.0
---

# NXD Data Product Debugging

Diagnose from evidence first, then patch the smallest source, config, dependency, resource, or contract issue.

## Setup

- Confirm `nxd-setup` has selected the mesh and produced `<session_config>`.
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
   [nxd-data-product-builder/reference/troubleshooting.md](../nxd-data-product-builder/reference/troubleshooting.md)).
4. **Patch the smallest surface** that the confirmed cause points to.
5. **Verify** — re-run the check that failed, then re-read status/logs.
6. If not fixed, return to step 1 with the new evidence.

The symptom→cause→fix catalog backing steps 2–4 lives in
[troubleshooting.md](../nxd-data-product-builder/reference/troubleshooting.md)
(deployed-runtime failures) and
[common-pitfalls.md](../nxd-data-product-builder/reference/common-pitfalls.md)
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

When many DPs fail at once, or a DP `Failed` with no clear app-level cause, rule
out cluster/infra health before blaming the DP (local dev only — confirm
`nxd describe config` shows the local cluster first):

```bash
kubectl get nodes -o wide                                  # Ready?
kubectl describe node <node> | grep -iE "MemoryPressure|DiskPressure|PIDPressure"  # all False?
kubectl get pods -A | grep -ivE "Running|Completed"        # broken pods anywhere
```

A CrashLooping `otel-collector-targetallocator` in `nxd` is **benign** (telemetry
only — it's the source of the `:4317 connection refused` spam, not a DP cause).
A node with no pressure + Ready means the failure is in the DP/kernel, not infra.
Stale `rpc-<hash>` pods stuck `Terminating` (hours/days old) in `dps` wedge new
rpc servers ("waiting up to 5 minutes for previous resource to delete"); they are
safe to force-delete ONLY after their owning DP is undeployed and ONLY on the
confirmed-local cluster. A mismatched pip-registry wheel set (`nxd_core` vs
`nxd_data_product` at different versions) makes DPs fail at runtime with
`Error deserializing context: missing field secret_password` — rebuild a matched
set with the `pip-registry` skill.

## Failure Triage

- Config/spec parse error: inspect `spec.py`, model imports, service URLs, infra profile names, and transform parameter names.
- Dependency install or init failure: inspect init logs, `requirements.txt`, `pyproject.toml`, `.nxdignore`, package indexes, and flat-layout packaging. `ModuleNotFoundError: No module named 'nxd.data_product'` means `requirements.txt` is missing the SDK — both `nxd_core` and `nxd_data_product` are always required.
- Stuck in `PROVISIONING`: the environment is still installing — a dependency install is failing (bad package name, unavailable version, unreachable index). Read init logs. `PROVISIONING` is a state, not yet an error.
- Startup timeout: inspect init logs and runtime logs before assuming timeout. OOM can appear as startup timeout. Discriminate via the status reason / exit 137, not by guessing.
- Transform runtime error: reproduce with the local transform runner, then fix parsing, type conversion, chunking, output writes, or API paging.
- Output write failure: check driver context, service credentials, table/path/index names, schema settings, and promise code. For pgvector: `Embedding column is not type Vector` means the embedding attribute was declared `string()` instead of `vector_embeddings(<dim>)`; a dimension-mismatch error means the declared dimension ≠ the model output (see troubleshooting.md §4). **The pgvector driver provisions the column type FROM the model, so fixing the spec is NOT enough on its own: the existing table already has the wrong (`TEXT`) column. The fix must RE-PROVISION the table — re-launch the data product (or drop the table) so the column is recreated as `vector` — not merely re-run the transform against the wrong column.** The same applies to a `vector_embeddings(N)` dimension change.
- Row count multiplies on every (green) run = an **idempotency** bug, not a crash — do not hunt failure logs. Cause: chunk ids generated with random UUIDs, so every run INSERTs fresh rows. Fix: deterministic ids (`uuid.uuid5(namespace, f"<source>:{record_key}:{chunk_index}")`) so reruns upsert instead of insert. **langchain/pgvector upserts via `ON CONFLICT` on `langchain_id`, which only works if the table has a unique index — add `CREATE UNIQUE INDEX IF NOT EXISTS ... ON <table> (langchain_id)` at transform start.** Do NOT "fix" it by deleting all rows each run (`write_mode("overwrite")` / truncate-then-write) unless that is an explicitly chosen strategy, and do not blame the schedule.
- Policy or contract failure: switch to `nxd-complying-with-failing-policy`.
- **Semantic-layer / rpc-MCP DP won't serve (State=Failed, or Broken in `nxd mcp health`, or `tools/list` empty).** These DPs (the `nxd.experimental.semantic` kind, exposing `list_models`/`describe_model`/`run_semantic_query`) have a stack of non-obvious deploy traps — diagnose in this order:
  - **First, filter telemetry noise.** Pod logs spam `BatchLogProcessor.ExportError ... tcp connect error ... :4317 connection refused` — that is the OTel collector, NOT the failure. Always `grep -ivE "BatchLogProcessor|ExportError|opentelemetry|4317"` before reading.
  - **`State=Failed` but the marker promise failed (`Field MARKER_ID not found in the model`):** promise verification runs **BEFORE** the transform, so a DP that seeds its marker/base tables **in the transform** fails verify (tables don't exist yet). Seed at **provision time** instead: an `@on_provision` function wired via `.provision(script("provision.py"))` (runs before verify). The transform must NOT also seed.
  - **`ModuleNotFoundError: No module named 'transform'` (or registry/tools) in `/app/provision/__provision__.py`:** the provision entrypoint runs from a `provision/` subdir whose `sys.path` excludes the DP root. `provision.py` must be **self-contained** — no bare sibling imports (`from registry import ...`); inline any needed value (e.g. hardcode the `<MODEL>_SEMANTIC` view name).
  - **DP flaps `Started`↔`Failed`, kernel logs `Timeout waiting for execution to start`:** a compute pod (transform or provision) is not coming up within the startup budget. Provision: raise it via `data_product(..., provision_timeout_secs=600)` (cold venv build > default 180s). Transform: it has no timeout knob — keep the transform a **no-op** (seeding lives in provision) and verify a stale/zombie `rpc-<hash>` pod isn't blocking the compute slot (`kubectl get pods -n dps | grep -E "Terminating|^rpc-"` — a stuck-Terminating rpc pod wedges redeploys with `waiting up to 5 minutes for previous resource to delete`).
  - **`tools/list` returns `[]` / `Unknown tool: list_models` (rpc pod Running):** the `code()` rpc-tool extractor carries imports + top-level def/class but **DROPS module-level `=` assignments**. A `@mcp.tool(description=_CONST)` referencing a module constant, or a module-level `_DIALECT` singleton used in the tool body, raises `NameError` at rpc-server load → 0 tools register. Fix in `tools.py`: **inline the description literal** into each `@mcp.tool(...)` and **build per-call state (the dialect) INSIDE the function body**.
  - **`run_semantic_query` → `'Context' object has no attribute 'connector_params'`:** the rpc runtime binds the tool's `snowflake` arg to a raw `Context`, not a `Snowflake`. Convert at the top: `from nxd.data_product.context import Snowflake; if not hasattr(snowflake, "connector_params"): snowflake = Snowflake.from_context(snowflake)`.
  - **`ValidationError: Facade view output(s) cannot be combined with .transform()`:** an rpc/MCP semantic DP cannot use the facade `as_view` pattern — the validator forbids `as_view` + `.transform()`, and rpc-tool sibling bundling REQUIRES a transform. Use the **self-seed** pattern (plain `storage(...)`, seeding in `@on_provision`), not facade.
  - **Transform `CREATE VIEW` fails binding a table from another DP's schema:** the transform must reference ONLY this DP's own tables. Never run the compiler's `native_semantic_view_ddl`/`plain_view_ddl` when the registry has a cross-DP join (they emit a JOIN to a crosswalk table in another DP's schema). Hand-author a single-table `<MODEL>_SEMANTIC` view.
  - **Discovery:** `nxd mcp health --format json` (NO `--mesh` on a default-mesh local config — it panics `does not have meshes defined`). `derived_state: Broken` + `tool_count: 0` = the breaker opened on an `empty_tool_list` probe (see the `tools/list []` entry above).
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
