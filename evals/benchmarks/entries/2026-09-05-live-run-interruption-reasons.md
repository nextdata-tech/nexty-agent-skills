---
id: 2026-09-05-live-run-interruption-reasons
date: 2026-09-05
label: "structured terminal reasons for an interrupted live scenario run"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — structured terminal reasons for an interrupted live scenario run

## Notes

This change is entirely in the live runner: the Claude adapter, the live
session transport, the drift canary's working directory, and the report. No
skill under `src/` changes, no scenario or answer sheet changes, and no agent
prompt changes. A public scenario run would drive the same skills against the
same fixtures and produce the same judge checks, turns and tokens before and
after, so no runnable arm can distinguish it.

That is not incidental — it is the point of the change. The behaviour being
fixed only appears when a live run *fails to produce* a graded turn, which is
exactly the case an eval arm cannot represent: the arm either runs to
completion, in which case none of this code executes, or it does not, in which
case there is no measurement to pair. The whole defect (issue #238) is that
those runs reached `report.json` as `ungraded` and nothing else, so a scenario
defect, a provider usage ceiling, and two runs contending on one store were
indistinguishable to a reader. The evidence therefore has to be deterministic
tests over real subprocesses, not a scenario number.

Three concrete faults are closed:

1. `LiveSession` read the child's stderr with a blocking `read()` on both the
   timeout and the EOF path. A wedged child holds that pipe open, so the
   bounded turn deadline became an unbounded parent wait — the parent had a
   deadline and still hung past it. Only already-buffered bytes are taken now.
2. Nothing gateable survived an interruption. `TurnResult` carries a
   closed-vocabulary `failure_reason` and the sanitized `last_mcp_call`; the
   engine keeps the classification from the first interrupted turn; every run
   in `report.json` and `summary.txt` carries an `interruption` block, null
   members and all, so a consumer reads one shape either way.
3. The live drift canary probed and built the checked-in package in place. The
   supervisor uses the closure as its working directory and writes run state
   beside it, so two concurrent live runs shared one store and the loser
   reported `database is locked` — contention wearing the costume of a canary
   defect. Each live run now gets its own copy; replay still reads the package
   directly and is byte-identical.

None of these reasons is a pass. `provider_session_limit`,
`run_budget_exhausted`, `child_no_terminal_result`, `child_exited_early` and
`shared_runtime_contention` all describe a scenario that was not tested, and
the README says so where an operator will read it.

### Follow-up — classify the runner's own spend cap

The September 23 live B1 run stopped on operator turn 12 of a 22-turn budget;
its terminal diagnostics record Claude Code's structured
`error_max_budget_usd` subtype. The runner now preserves that as
`run_budget_exhausted`, distinct from a provider or account usage limit. The
run remains invalid/incomplete; no behavioral gate result is promoted to
success. This is a harness-only diagnostic change with no scenario arm and
remains `NO_EVAL`. A separate current-main attempt stopped immediately at the
provider session limit; the two interruptions remain distinct.

## Evidence

- `evals/dp-scenarios/tests/test_runner_live_deadline.py` — five tests against
  real child processes: a silent child stops at the deadline and is reaped, a
  provider ceiling announced on stderr is named rather than reported as a bare
  stall, a child exiting on a locked store is named as contention, a silent
  exit still gets a reason, and three concurrent starts each finish bounded
  with three distinct reaped children. The first and last fail by hanging to
  the pytest bound against the previous blocking-`read()` implementation.
- `evals/dp-scenarios/tests/test_runner_canary_isolation.py` — the live canary
  never probes the checked-in package in place, its copy is removed on return,
  three concurrent canaries get three distinct closures across six recorded
  probe/build calls, and a replayed canary still reads the package directly.
- `evals/dp-scenarios/tests/test_runner_claude_adapter.py` — the adapter
  boundary: a stalling child names the missing terminal result while still
  retaining its partial transcript, a stderr ceiling outranks a bare stall, and
  the last MCP call survives onto the turn that stopped.
- `evals/dp-scenarios/tests/test_runner_failure_reasons.py` — the vocabulary
  itself, including that structured run-cap subtypes outrank prose, free-text
  mentions of the subtype do not classify, a provider ceiling outranks a lock
  message in the same text, and ordinary agent prose is never classified.
- `evals/dp-scenarios/tests/test_runner_tier.py` and
  `evals/dp-scenarios/tests/test_runner_report.py` — the reason, detail and last MCP call survive
  the whole path into `report.json` and `summary.txt`; budget exhaustion is
  reported as invalid rather than success, and a clean run reports the same
  block with null members.
