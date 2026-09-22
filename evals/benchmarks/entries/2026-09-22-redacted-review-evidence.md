---
id: 2026-09-22-redacted-review-evidence
date: 2026-09-22
label: "preserve reviewer evidence when Agent prompts are redacted"
plugin_version: 0.51.6
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — preserve reviewer evidence when Agent prompts are redacted

## Notes

Harness-only. The Claude adapter already redacts reviewer prompts before
persisting replay artifacts because they contain retained supervisor paths and
source material. The construction gate previously depended on those prompts,
so a completed reviewer could be reported as absent. The adapter now records a
minimal runner-owned observation containing only validated booleans and the
normalized closure/round identity; the gate still rejects incomplete,
background, unbound, or metadata-only children. No qualified before/after
scenario comparison is available: the post-change B1 live attempt was
invalidated immediately by the provider session limit.

## Evidence

- `evals/dp-scenarios/tests/test_runner_claude_adapter.py` — derives the
  report-safe observation while the raw prompt is still in memory and verifies
  that the persisted prompt is redacted.
- `evals/dp-scenarios/tests/test_grading_gates.py` — accepts only a complete
  runner-owned observation and rejects an unbound one.
- `evals/dp-scenarios/tests/test_runner_session.py` — preserves the new field
  through replay serialization and reconstruction.
