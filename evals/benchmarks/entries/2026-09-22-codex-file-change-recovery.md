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

The carrying B1 Codex attempt ended incomplete after a malformed native file
change, so it is not a before/after scenario result and no scenario pass is
claimed. The focused regression suite exercises the corrected event handling,
terminal classification, review lock, bounded review reader, and MCP proxy.

## Evidence

- `evals/dp-scenarios/tests/test_runner_codex_adapter.py` — rejected native
  file changes remain recoverable and non-review requirement reports do not
  clear the review lock.
- `evals/dp-scenarios/tests/test_operator_engine.py` — timeout wins over a
  simultaneous environment diagnostic.
- `evals/tests/test_desktop_stdio.py` — the runner-owned review reader accepts
  the reviewer’s real bounds and remains path/sensitivity constrained.
