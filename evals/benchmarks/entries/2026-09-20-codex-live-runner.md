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
guard, and the Codex live transport now enforces the critical boundary in the
persistent runner-owned Desktop session: a successful capture that returns a
pending review arms a Codex-only guard, blocked inspect/list/check/prepare
operations receive a corrective `isError` MCP result, and the guard clears
after either a valid clear report or a valid `workflow/review_findings` relay.
The latter is necessary because an authorized remediation reset is the next
legal action after findings; the proxy must release that reset to the
supervisor. Claude and replay paths do not enable this guard.

The available live Codex smoke is provider evidence only. The prior B1 Codex
runs were `ungraded` because the agent re-entered an existing workflow after a
valid capture and then timed out; the latest retained run had no source/build
evidence and is not a pass or a benchmark comparison. A follow-up run reached
the valid `review_pending` state but repeatedly reset/listed/inspected the
workflow instead of dispatching the required child; it was stopped after the
trace established that second workflow-control defect. The carrying proxy test
now reproduces that transition and proves the illegal operations are answered
without reaching the supervisor, while the matching report reopens normal
operation. The first run with explicit Codex collaboration and the child-wait
parser still ended `ungraded` with `turn_timeout` during closure authoring,
before the reviewer path. The next run reached the reviewer and produced a
completed child result, but Codex sent the bounded review report as a
JSON-encoded string instead of the required object; the supervisor correctly
rejected it as `workflow/review_incomplete`, and that run also ended
`ungraded`/`turn_timeout`. Neither is a pass or a benchmark comparison. Full
local validation after the latest runner changes is 3196 passed, 37 skipped,
1 warning. A subsequent run sent the report as an object and reached the
reviewer finding path, but mutated/reset the captured workflow before returning
the non-clear finding; the supervisor rejected the stale operation and the run
ended `ungraded`/`turn_timeout`. The latest prompt fix makes captured inputs
immutable until reporting and requires non-clear reports to stop for operator
adjudication. A future measured entry still requires a complete authenticated
scenario run with a terminal report. The first run after this guard fix reached
four successful resets, a clear review, and `check_data_product`, proving that
the findings-to-reset path now reaches the supervisor. It still ended
`ungraded`/`turn_timeout` because the Codex parent did not complete that turn
and never reached validation, admission, publication, or query. This is
incomplete provider evidence, not a scenario pass; a timeout result is not
benchmark evidence of skill quality.

## Evidence

The carrying tests are
`evals/dp-scenarios/tests/test_runner_codex_adapter.py`,
`evals/dp-scenarios/tests/test_run_local_claude.py`, and
`evals/tests/test_desktop_stdio.py`.
