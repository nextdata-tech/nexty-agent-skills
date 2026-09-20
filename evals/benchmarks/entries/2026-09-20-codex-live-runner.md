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

The available live Codex smoke is provider evidence only. The prior B1 Codex
runs were `ungraded`/runner-limited because resumed `codex exec` processes lost
the MCP catalog; none is a pass or a benchmark comparison. A future measured
entry requires a complete authenticated scenario run with a terminal report.

## Evidence

The carrying tests are
`evals/dp-scenarios/tests/test_runner_codex_adapter.py` and
`evals/dp-scenarios/tests/test_run_local_claude.py`.
