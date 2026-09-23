---
id: 2026-09-23-codex-native-state-retention
date: 2026-09-23
label: "Codex native continuation preserves private app-server state"
plugin_version: 0.52.1
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — Codex native continuation preserves private app-server state

## Notes

Harness-only runner lifecycle fix. No scenario arm measures whether a provider's
native thread state survives restarting the local adapter process, so a
scenario score would not distinguish this change. The previous Codex B1 resume
attempt was ungraded: `thread/resume` returned “no rollout found” because each
adapter process created and then deleted a disposable `CODEX_HOME`. Native
continuation now retains the isolated app-server home under the private
per-scenario, per-epoch run root. Non-native runs remain disposable. This is
not evidence that B1 passes; a fresh B1 run and a completed graded report are
still required.

Provider home state can include transcripts and tool results. It remains
owner-only, outside the agent workspace and exported evidence bundle, and the
host auth handle is only symlinked, never copied or read by the harness.
Codex may add a local `trust_level = "trusted"` project marker while opening
the app-server. Resume validation permits only that marker for the current
workspace and rejects any other project marker or persisted setting. A trusted
project may activate workspace-local Codex configuration, so resume also fails
closed when the agent workspace contains `.codex/`. A checkpoint resume after
this adjustment is still needed to prove continuity. The app-server excludes
`/tmp` and `$TMPDIR` from default workspace-write roots so the retained provider
home is not exposed through the broad temporary-directory allowance.

## Evidence

- `evals/dp-scenarios/tests/test_runner_codex_adapter.py` verifies fake
  app-server state survives adapter close/reopen and that the saved thread can
  resume; the auth handle remains a symlink.
- `evals/dp-scenarios/tests/test_runner_environment.py` verifies the runner
  passes the per-run private Codex home only for native Codex continuation.
