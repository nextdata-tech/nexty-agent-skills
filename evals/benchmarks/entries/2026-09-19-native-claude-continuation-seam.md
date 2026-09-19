---
id: 2026-09-19-native-claude-continuation-seam
date: 2026-09-19
label: "add an explicit opt-in native Claude continuation seam"
plugin_version: 0.51.3
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — add an explicit opt-in native Claude continuation seam

## Notes

Harness-only. No skill under `src/` and no scenario declaration changed, so no
runnable public arm can distinguish this change. This is an explicit bounded
continuation seam, not B1 evidence or a claim that B1 passes.

Native continuation is opt-in and remains distinct from handoff. It persists
only a canonical Claude UUID and an execution-identity digest, requires an
explicit persistent run root, locally replays and verifies the committed
operator prefix, starts at the next operator turn through Claude's native
`--resume` path, and continues the remaining turns in that session.
Redacted touched-file observations are rehydrated only from the retained
workspace and must match their committed hash and size. Unsupported
environment reuse, changed prefix files, and identity mismatch fail closed.

## Evidence

The carrying tests are
`evals/dp-scenarios/tests/test_runner_checkpoint.py`,
`evals/dp-scenarios/tests/test_runner_session.py`,
`evals/dp-scenarios/tests/test_runner_claude_adapter.py`,
`evals/dp-scenarios/tests/test_runner_environment.py`, and
`evals/dp-scenarios/tests/test_runner_tier.py`.
