---
id: 2026-09-16-runner-partial-json-deadline
date: 2026-09-16
label: "bound partial JSON responses in the live runner"
plugin_version: 0.49.6
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — bound partial JSON responses in the live runner

## Notes

No scenario isolates a child that writes an incomplete JSONL response and
keeps its stdout open. The live B1 run timed out after an answered
`advance_workflow` call; it did not exercise this parent-side partial-line
path. A live before/after comparison would therefore measure provider timing,
not this runner safety fix.

The runner now reads its child stream through a deadline-bounded byte buffer,
so a partial line cannot turn the outer turn limit into an unbounded
`readline()` wait. The change preserves a partial EOF's single-consumption
semantics and keeps interruption results reportable rather than successful.

## Evidence

- `evals/dp-scenarios/tests/test_runner_live_deadline.py` — a partial line
  with an open pipe reaches the timeout and cleans up the child; a partial EOF
  is consumed once before a retry observes EOF. Both fail against the previous
  blocking `readline()` implementation.
- `evals/dp-scenarios/tests/test_runner_session.py` — existing live-session
  protocol coverage carried alongside the deadline regression suite.
