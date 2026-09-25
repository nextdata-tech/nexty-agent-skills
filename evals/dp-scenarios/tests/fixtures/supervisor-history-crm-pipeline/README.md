# Supervisor history fixture (S3): crm-pipeline, B1 live PASS

A minimized, secret-free snapshot of one real supervisor data directory
(`desktop-state/`) and the runner-owned artifact directory (`artifacts/`) from a
live dp-scenarios run. It exists so prerequisite **P2** (supervisor history
artifacts) and the **B7** identity check can be written and tested against
records the supervisor actually produced, not hand-built ones.

`MANIFEST.json` lists every file with its size, sha256, the reason P2 needs it,
and which P2 output it feeds.

## Provenance

| | |
|---|---|
| Scenario | `crm-pipeline` (B1), epoch 1, trial 0, tier `core`, 22-turn budget |
| Result | PASS (`output/report.json` of the source run) |
| Agent | Claude Sonnet, effort high, skill pack 0.52.9 |
| Supervisor | built from the `nxd-failure-facts` branch, binary sha256 `9ebee32b…5e79`. That branch landed as nxd main `e3f4860` ("surface failed contracts and exception class for failed runs", #7959). |
| Source dir | a local live-run epoch directory for `crm-pipeline` (`desktop-state/` and `artifacts/`) |
| Builder | an out-of-repo spike script (deterministic: two rebuilds are byte-identical) |

Schema check against the pinned supervisor: `state.sqlite3` and the kernel
`event_store` schemas are identical (`sqlite3 .schema` diff is empty) to those in
the B5 `inventory-position` live run, which ran the pinned `e3f4860` main build. The
B3 run  has the same schema too. Release records are
`nxd-release-v1` in all three runs.

B1 was chosen over B3 because it has more history: two workflows (`crm-pipeline`
and the switched-to `crm-pipeline-current-v2`), one published run each, five
rejected independent reviews, seven resets, and one failed validation with an
operation diagnostic. B3 has one workflow, one run, and no failures.

## What happened in the session (for orientation)

- Turns 1–13 work on workflow `crm-pipeline`. Its only run
  (`run-e96e6a40…`, publish_seq 1, request `run-crm-pipeline-1`) was
  admitted in turn 4 and published. Later capture/review rounds (generations
  4–8) reset the workflow. The final re-validation
  (`validate-crm-pipeline-2`, turn 13) **failed** with
  `validation/existing_workflow_unsupported`. No second run was admitted.
- Turn 14 moves to a new workflow, `crm-pipeline-current-v2`. It builds
  `run-03552f49…` (publish_seq 1). Turns 17+ query that product
  (`resume_data_product`, then `run_semantic_query` against the loopback
  endpoint).
- `artifacts/supervisor-facts.json` names the v2 run, because the session
  ended on that workflow. The existing `_update_from_state_dir` reproduces it
  exactly when run on this fixture with both run ids in `built_runs` and
  `workflow="crm-pipeline-current-v2"`.

## What was stripped or changed

1. **Host paths rewritten** everywhere, including inside SQLite TEXT and BLOB
   cells:
   - `<RUN_ROOT>` = the source epoch dir
   - `<OUTPUT_ROOT>` = the run output root
   - `<PLUGIN_ROOT>` = the temporary skill-pack install
   - `<TMPDIR>` = the macOS per-user temp dir
   - `<NXD_CHECKOUT>` = the nxd worktree the supervisor was built from
   - `<HOME>`, `<HOST_PATH>` = other host paths (no occurrences remain)

   Because of this, sha256 values that cover a rewritten field no longer match
   it. Examples: `wf_evidence.private_json.retained_root`,
   `wf_instances.*_path`, and `build-record.json.closure_path`. Hash
   *references* (ids, `*_sha256` strings) are unchanged, so joins still work.
   Do not re-verify content hashes over rewritten fields.
2. **SQLite normalized.** Each DB was read from a scratch copy with its WAL
   checkpointed (the source dir was never opened by sqlite), then rebuilt
   row-by-row in primary-key order into a single file with
   `journal_mode=DELETE`, then VACUUMed. No `-wal`/`-shm` files. All rows of
   all tables are kept, and `sqlite_sequence` is preserved.
3. **Credentials.** The run held no live secret on disk: the harness had
   already redacted MCP bearer/session tokens to `"<redacted>"` in tool
   results, and `infra-profile.yaml` names the token *environment variable*
   (`NXD_EVAL_SOURCE_TOKEN`), not a value. The loopback mock URL
   (`http://127.0.0.1:<port>`) is kept, and the definition files are
   byte-identical to the originals so `definition.json` hashes still verify.
4. **Captures.** Only 3 of the 9 retained captures are kept:
   - the two captures that were admitted for runs
   - `crm-pipeline`'s current capture, the one whose validation failed

   In each kept capture:
   - `.gitignore` is dropped: committed, it would hide `infra-profile.yaml`
     from git.
   - `self_check.py` is replaced by a 3-line stub. It was a 185 KB
     supervisor-provided copy; the stub records the original size and sha256.
   - `SENSITIVE` is kept on purpose: it is the marker P2's capture snapshot
     must honour.

   `wf_evidence` / `wf_operations` rows still reference the 6 dropped
   captures.
5. **Blueprints.** Only the two `retained_blueprint_path` targets named by
   `wf_instances` are kept. The other 4 retained blueprints are dropped.
6. **Dropped outright:**
   - `generations/` (published DuckDB artifacts, 1.8 MB each)
   - `leases/`, `gc/`, `proposals/`
   - empty `run-views/`, `checks/`, `validation/`, `validation-receipts/`,
     `staging/`, `proposal-work/`
   - every `*.lock`, `supervisor.pid`, `topology.lock`
   - agent workspace copies (`artifacts/closure`, `artifacts/nxd-jobs`,
     blueprint drafts, HTML renders)
   - `session-replay.json` (9 MB; the same tool calls as the observations)
   - `server-counters.json`, `source-evidence.json`, `capability.json`
     (source-side, used by P3 rather than P2)
   - `review-record.json` (agent-authored)
7. **`artifacts/operator-observations.json` trimmed.** Same top-level schema
   and all 22 turns are kept, with these changes:
   - `tool_calls` keeps only the 93 `mcp__nxd-desktop__*` calls, in their
     original order, with `name`, `arguments`, `result` and `observation`
     intact. The 407 Read/Edit/Write/Glob/Grep/Agent/Skill/ToolSearch calls
     are dropped.
   - `files_touched` is emptied and `transcript_delta` is removed.
   - The top-level `tool_call_count` (500) still counts the original calls,
     so it no longer equals the number of kept calls.
   - The JSON is re-serialised with sorted keys.

## Record schemas found (what P2 builds on)

### `desktop-state/state.sqlite3` (`wf_state_meta.schema = nxd-workflow-state-v2`, version 2)

Rows in this fixture: `workflows` 2, `runs` 2, `wf_admissions` 2, `wf_events` 49,
`wf_operations` 36, `wf_requests` 36, `wf_requirements` 8, `wf_evidence` 25,
`wf_operation_diagnostics` 1, `run_diagnostics` 0, `workflow_removals` 0.

- **`workflows`**: one row per workflow; the current pointer.
  - Columns: `workflow_id` PK (the human id, e.g. `crm-pipeline`),
    `workflow_key` (`wf-sha256-v1-<64hex>`, the directory name under
    `workflows/` and `kernel-state/`), `status`, `run_id`,
    `current_artifact_id`, `current_release_basename`,
    `next_unallocated_publish_seq` (TEXT).
  - `status` values: `Active` / `Published` / `Rerunnable`.
- **`runs`**: the run lifecycle record, one row per admitted run.
  - Columns: `run_id` PK, `workflow_id`, `artifact_id`, `definition_id`
    (`sha256-v1:<hex>`), `publish_seq` (TEXT), `release_basename`,
    `base_artifact_id`, `base_release_basename`, `artifact_size`,
    `artifact_sha256`, `checkpoint_sha256`, `compiler_id`,
    `runtime_bundle_id`, `verification_json`, `verified_at_unix_ms`,
    `published_at_unix_ms`, `gc_not_before_unix_ms`, `admission_id`,
    `control_epoch`, `status`.
  - `verification_json` is `nxd-verification-v1`:
    `{outcome, row_counts{table: str}, table_sha256{table: str}}`.
  - Timestamps are TEXT unix ms.
  - `status` values: `Running`, `Verified`, `Promoting`, `PointerFlipped`,
    `Published`, `RolledBack`, `Failed`, `Cancelled`, `Superseded`.
  - **This table has no start timestamp.** The start is the admission (see
    below) or the kernel `RunStarted` event.
- **`wf_admissions`**: the run *start* record.
  - Columns: `admission_id` PK, `admission_sha256`, `workflow`,
    `request_id` (the agent's `advance_workflow` request id, e.g.
    `run-crm-pipeline-1`), `run_id`, `artifact_id`, `definition_id`,
    `publish_seq` (INTEGER), `control_epoch`, `status`, `dossier_json`.
  - `status` values: `admitted` / `cancel_requested` / `terminal`.
  - `dossier_json` is `nxd-workflow-admission-v2`:
    `{workflow, request_id, run_id, artifact_id, definition_id, publish_seq,
    control_epoch, contract{version, sha256, snapshot}, policy{…},
    blueprint{raw_sha256, semantic_sha256, …}, consent{…}, budget_secs,
    capture_id, capture_sha256, process_bound_validation{…},
    evidence[{evidence_id, requirement_id, handler, generation, source,
    identity{…}, …}]}`.
- **`wf_events`**: the workflow event log.
  - Columns: `event_id` AUTOINCREMENT, `workflow`, `revision`, `code`,
    `operation_id`. **No timestamps.**
  - Codes seen: `workflow/prepared`, `workflow/session_decision`,
    `workflow/capture_queued`, `workflow/requirement_satisfied`,
    `workflow/requirement_queued`, `workflow/review_findings`,
    `workflow/review_satisfied`, `workflow/reset`,
    `workflow/admission_queued`, `workflow/run_admitted`,
    `validation/existing_workflow_unsupported`.
- **`wf_operations`**: one row per agent request.
  - Columns: `operation_id` PK, `request_id`, `workflow`, `started_epoch`,
    `requirement_id`, `generation`, `subject_sha256`,
    `dependency_evidence_sha256`, `handler_policy_sha256`, `status`.
  - `status` values: `queued`, `running`, `succeeded`, `failed`,
    `unavailable`, `indeterminate`, `superseded`, `cancelled`.
  - **`wf_requests`** maps `request_id` to the MCP `operation`
    (`prepare_workflow` / `advance_workflow` / `reset_workflow`), a
    `request_sha256`, and `operation_id`.
- **`wf_requirements`**: `(workflow, requirement_id)` →
  `ordinal, handler, subject_slot, depends_json, accepted_sources_json,
  generation, subject_sha256, handler_policy_sha256, status`.
  - `status` values: `blocked`, `pending`, `running`, `satisfied`,
    `rejected`, `stale`, `unavailable`.
  - Requirements: `consent`/`session-confirmation-v1`,
    `capture`/`capture-v1`, `review`/`independent-review-v1`,
    `validation`/`generator-validation-v1`.
- **`wf_evidence`**
  - Columns: `evidence_id` PK, `workflow`, `requirement_id`, `generation`,
    `source`, `outcome`, `identity_json`, `private_json`,
    `operation_id`, …
  - `source` values: `session_reported` / `supervisor_execution`.
  - `outcome` values: `satisfied` / `rejected` / `failed`.
  - Review `private_json` is `nxd-conversation-review-v1`:
    `{verdict: clear|findings, findings[{id, severity: blocking|advisory,
    description}], rejection_code}`.
  - Validation `identity_json`:
    - on success: `{validation_id, definition_id, workflow, budget{…},
      checker{…}, …}`
    - on failure: `{validation_failed: true, diagnostic_codes[…]}`.
- **`wf_operation_diagnostics`**: `operation_id` PK, `workflow`,
  `requirement_id`, `diagnostic_json` =
  `{phase, code, detail, recovery}`. The one row here is
  `{phase: supervisor_preflight, code: validation/existing_workflow_unsupported, recovery: stop}`.
  This is the only failure fact in the fixture.
- **`run_diagnostics`** (empty here): `run_id` PK, `workflow_id`,
  `outcome`, `timeout_phase`, `recorded_at_unix_ms`, `summary`,
  `diagnostic_json`.
  - The empty table comes from the pinned `e3f4860` source
    (`components/desktop/supervisor/src/diagnostics.rs`, `RunDiagnostic`).
  - `diagnostic_json` is `nxd-run-diagnostic-v5`. Fields:
    - `schema, run_id, workflow_id, started_at_unix_ms,
      recorded_at_unix_ms`
    - `outcome` ("failed"), `code?`, `timeout_phase`, `last_phase`,
      `error`
    - `budget`, `elapsed_ms`, `timed_out`, `expired_budget(_secs)`,
      `transform_stage?`, `transform_http_status?`
    - `failed_contracts?: [{contract, model, failed_count}]`,
      `exception_class?`
    - `phases[{phase, at_ms}]`, `child_*`, `staging{…}`,
      `stdout/stderr{total_bytes, truncated, lines}`, `log_reference`
  - Phase strings: `snapshot_compiled`, `run_view_created`,
    `kernel_spawned`, `host_booted`, `transform_dispatched`, … ,
    `promise_verdict_received`, `staging_verified`,
    `checkpoint_verified`, `generation_materialized`, `published`.
- Other tables:
  - `wf_instances` (per-workflow contract, policy, blueprint, and consent
    snapshots; paths rewritten)
  - `wf_contracts`, `wf_active_policy`, `wf_eligibility`,
    `wf_admission_evidence`, `workflow_removals`

### `desktop-state/workflows/<workflow_key>/`

- `releases/release-<20-digit seq>-<run uuid>.json` is `nxd-release-v1`:
  `{workflow_id, workflow_key, publish_seq (str), run_id, definition_id,
  artifact_id, artifact_size, artifact_sha256, checkpoint_sha256,
  compiler_id, runtime_bundle_id, verification{nxd-verification-v1},
  published_at_unix_ms, gc_not_before_unix_ms}`. This is what
  `_published_releases` already globs.
- `admission-links/<release basename>.json` is
  `nxd-release-admission-link-v1`. It joins a release to its admission:
  `{workflow_id, workflow_key, release_basename, release_sha256,
  admission_id, admission_sha256, run_id, artifact_id, definition_id,
  publish_seq, control_epoch}`. The doubled `.json.json` suffix is real.
- `current` is a text pointer, `nxd-current-v1`:
  `sequence=`, `release=`, `release_sha256=`.

### `desktop-state/definitions/sha256-v1/<hex>/` (the compiled definition that ran)

- `definition.json`: `nxd-definition-manifest-v1`, a
  `{definition_id, files[{path, size, sha256}]}` integrity list.
- `manifest.yaml`: kernel manifest.
  - **Output promises** are under
    `output.ports.<port>.promises.validation[]`, one entry per promise:
    `{name, description, models[], source: contracts/promises/<name>.py,
    computeService{driver}}`. A promise with `source` is a script
    verifier. There is no explicit "kind" or "attachment" field; attachment
    is implied by the location (`output.ports.duckdb.promises`).
  - Schema-shape promises are listed separately under
    `promises.model: [model…]`.
  - Input expectations would appear under `inputs`, which is empty here.
- `deployment-spec.yaml`, `models.yaml` (semantic metadata in
  `__nxd_semantic__`), `infra-profile.yaml`, `transform/main.py`,
  `contracts/promises/*.py`, `data/…`, `csv-source-path`.

### `desktop-state/kernel-state/<workflow_key>.sqlite3` (per-product kernel store)

- **`event_store`**: `id, dp_name, event_index, event_type, event_timestamp`
  (ISO), and `event_data` (JSON).
  - Event types per run: `SkipRun`, `AllExpectationsChecked`,
    `Provisioned`, `LoadedPolicies`, `RunStarted`, `StatusChange`,
    `RunStats{success, start/end_timestamp, task_id}`, `CheckedPromise`
    (×5), `AllPromisesChecked`.
  - `CheckedPromise` shape: `{type, name, description, models[], result,
    context{results[{outcome, failed_count, extra_info_json}]}, output{…}}`.
  - Values observed:
    - `type`: `model_verification` (one per `promises.model` entry, named
      "Promises for model X") or `custom` (one per script promise, named
      with the manifest promise name)
    - `result`: `Success`
    - `results[].outcome`: `Pass`
  - These are the live enum strings B7 WP-D should pin. The failure
    spellings (`Failure` / `Fail`) are not in this fixture.
- **`state_store`**: `(namespace = dp_name, key)`. Keys: `state`,
  `transactions/v1`, and `status`. `status` holds
  `{running, policy_violations, failed_promises, run_failure,
  generic_failure, run_history[bool]}`.
- The kernel `task_id` / `run_id` is a bare UUID **unrelated** to the
  supervisor `run_id`. Join through `workflow_key` (the file name) and time
  order. One store accumulates every run of that workflow.

### `desktop-state/captures/sha256/<hex>/` (retained capture)

Authored closure files plus supervisor files:

- `build-record.json` (`nxd-build-record-v2`, per-stage status)
- `dp-blueprint.lock.json` (`nxd-dp-spec-lock-v3`)
- `dp-blueprint.approved.md`, `dp-blueprint.proposal.approved.json`
- the `SENSITIVE` marker

### `artifacts/` (runner-owned today)

- `supervisor-facts.json`: `{run_id, artifact_id, publish_sequence,
  per_model_row_counts, lifecycle_state}`.
- `query-results.json`: `{queries[{columns, rows}], rows}`. It has **no**
  turn, workflow, or endpoint attribution; P2 must add that.
- `operator-observations.json` `turns[]`: `{turn, phase, agent_message,
  operator_*, tool_calls[{name, arguments, result{content, is_error,
  tool_use_id}, observation}]}`.
  - The P2 tool-call log fields are `(turn, tool, workflow_id, run_id,
    endpoint)`. They come from `arguments.workflow`,
    `arguments.request_id`, `arguments.endpoint` (on
    `describe_models`/`run_semantic_query`), and from `run_id` in results:
    - `advance_workflow` results carry `admission{run_id, …}` and `events`
    - `inspect_run` carries `run{run_id, lifecycle, status, …}`
    - `resume_data_product` carries `run_id` and `semantic_endpoint`
  - Tokens appear only as `"<redacted>"`.

## Gaps P2 should know about

1. **No failed run.** No run in any available live run (B1, B2, B3, B5, B6)
   reached `runs.status = Failed` or wrote a `run_diagnostics` row. For
   `run-failures.json`, test against a synthetic row built from the
   `RunDiagnostic` v5 shape above, or against nxd's own test payloads
   (`supervisor/tests/mcp_server.rs` around the `failed_contracts` /
   `exception_class` assertions). The only real failure here is the
   operation-level `wf_operation_diagnostics` row.
2. **Brackets have no wall clock.**
   - Supervisor tables give `verified_at` / `published_at` in unix ms and
     kernel events give ISO times.
   - `wf_events` and the tool-call log have no timestamps.
   - So request attribution (B8 criterion 3) must bracket by **turn**: the
     turn whose `advance_workflow` result first shows `workflow/run_admitted`
     for a run, and the turn where `inspect_run` / `resume` / the release
     first shows it terminal.
3. **`admission` is sticky in `advance_workflow` / `reset_workflow` /
   `inspect_workflow` results.** After a run is admitted, every later workflow
   result for that workflow repeats the same `admission` object: here turns 5,
   8, 9, 12, 13 for crm-pipeline and 22 for v2. So the start turn is the
   **first** result carrying that `run_id`, which is also the one whose
   `arguments.request_id` equals `wf_admissions.request_id` (turn 4
   `run-crm-pipeline-1`, turn 14 `crm-pipeline-current-v2-start-run-1`).
4. **One publication per workflow here.** Multi-`publish_seq` ordering within a
   workflow is not exercised. The crm-pipeline second-run attempt was refused
   at validation instead.
