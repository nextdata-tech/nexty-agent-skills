---
id: 2026-09-20-codex-live-runner
date: 2026-09-20
label: "add a persistent Codex live-runner backend"
plugin_version: 0.51.3
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — add a persistent Codex live-runner backend

## Notes

Harness-only. No shipped skill or scenario declaration changed, so no existing
public scenario can distinguish the backend implementation. The Codex path is
an alternate authenticated live provider boundary, not a replay and not a
waiver of any gate.

The runner now keeps one `codex app-server --stdio` child for the whole live
run, configures the runner-owned `nxd-desktop` MCP server, and preserves the
opaque provider thread identity across operator turns. It stages the skill
pack instead of granting the source checkout, uses a disposable Codex
state/config home with only a symlink to the host-owned auth file, retains
partial MCP/message observations on timeout, and fails closed on malformed
events, unsupported server requests, or unmatched turn completion.

The Codex event bridge also records a completed provider-native `spawnAgent`
review child as shared `Agent` evidence only when the child returns content;
incomplete children, wait events, and background launches do not satisfy the
construction gate. The Codex prompt carries the workflow-v2 action-discipline
guard so an already-captured workflow is not re-entered through
`prepare_workflow`.

The available live Codex smoke is provider evidence only. The prior B1 Codex
runs were `ungraded` because the agent re-entered an existing workflow after a
valid capture and then timed out; the latest retained run had no source/build
evidence and is not a pass or a benchmark comparison. A follow-up run reached
the valid `review_pending` state but repeatedly reset/listed/inspected the
workflow instead of dispatching the required child; it was stopped after the
trace established that second workflow-control defect. A future measured entry
requires a complete authenticated scenario run with a terminal report.

## Evidence

The carrying tests are
`evals/dp-scenarios/tests/test_runner_codex_adapter.py` and
`evals/dp-scenarios/tests/test_run_local_claude.py`.
