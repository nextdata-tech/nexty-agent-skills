---
id: 2026-09-22-codex-file-change-recovery
date: 2026-09-22
label: "keep Codex file-change recovery and review state honest"
plugin_version: 0.51.6
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — keep Codex file-change recovery and review state honest

## Notes

Harness-only. No shipped skill or scenario declaration changed, so no public
scenario can distinguish this change. A rejected native Codex file change is
an agent/tool result and must remain recoverable within the turn; treating it
as an environment wedge invalidated the run before the agent could correct its
patch. The operator now also gives a simultaneous timeout precedence over a
diagnostic wedge, and the Codex review lock is released only for the review
requirement it actually satisfied.

The same hardening pass makes continuation provider-neutral, keeps Codex
thread identities resumable through the native checkpoint seam, persists a
minimal report for an abort before grading, and records report-safe terminal
and provider-usage diagnostics. Reviewer evidence now carries a prompt hash,
intermediate reviewer waits remain non-fatal, and the review proxy advertises
its synthetic reader before capture so Codex app-server catalog caching cannot
hide the tool from the child; each call still fails closed until the exact
allowlist is published, which is written atomically. Core Claude runs perform
a non-generative authentication preflight; provider usage limits remain an
external condition because the local CLI exposes no quota endpoint.

The carrying B1 Codex attempt ended incomplete after a malformed native file
change, so it is not a before/after scenario result and no scenario pass is
claimed. A fresh B1 attempt exercised the catalog fix: the reviewer made 50
successful runner-owned reads of the retained input, but the Codex app-server
never emitted the parent turn's terminal result and the run ended
`ungraded`/`turn_timeout`; that remains provider/runtime evidence, not a pass.
The focused regression suite exercises the corrected event handling, terminal
classification, provider continuation, durable abort reporting, review lock,
bounded review reader, authentication preflight, and MCP proxy.

## Evidence

- `evals/dp-scenarios/tests/test_runner_codex_adapter.py` — rejected native
  file changes remain recoverable, provider usage is report-safe, and
  non-review requirement reports do not clear the review lock.
- `evals/dp-scenarios/tests/test_operator_engine.py` — timeout wins over a
  simultaneous environment diagnostic.
- `evals/tests/test_desktop_stdio.py` — the runner-owned review reader accepts
  the reviewer’s real bounds and remains path/sensitivity constrained.
- `evals/dp-scenarios/tests/test_runner_checkpoint.py` and
  `evals/dp-scenarios/tests/test_runner_tier.py` — provider-neutral native
  continuation remains bound to the exact execution identity.
- `evals/dp-scenarios/tests/test_run_local_claude.py` and
  `evals/dp-scenarios/tests/test_runner_report.py` — authentication preflight
  and secret-safe abort/usage diagnostics.
