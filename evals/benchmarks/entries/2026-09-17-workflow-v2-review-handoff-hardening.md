---
id: 2026-09-17-workflow-v2-review-handoff-hardening
date: 2026-09-17
label: "harden workflow-v2 review handoff and contract evidence"
plugin_version: 0.51.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — harden workflow-v2 review handoff and contract evidence

## Notes

No public scenario can currently distinguish this follow-up. The latest B1
live run completed its operator script but the real supervisor failed every
`start_requirement` attempt during scratch validation, before publishing a
release. A score comparison would therefore measure the supervisor failure,
not the review-handoff changes.

This follow-up keeps the historical 120-second deadline entry immutable. It
adds the finalization reserve while treating supervisor-retained paths as
opaque contract values, clears stale handoff state on a replacement capture,
and fails early when an externally supplied MCP configuration has no
runner-owned supervisor data directory. It also records the reviewer scope and
typed timestamp contract corrections shipped with the same pack revision.

## Evidence

- `evals/dp-scenarios/tests/test_runner_review_guard.py` — documented
  workflow-v2 review-input shape, arbitrary retention layouts, stale-state
  clearing, path containment, and finalization cutoff.
- `evals/dp-scenarios/tests/test_runner_claude_adapter.py` — early data-dir
  failure and runner-owned review-root wiring.
- `evals/tests/test_review_closure_scope_contract.py` — structural notes are
  not promoted to consumer-impact claims.
- `evals/tests/test_spec_api_compiler_rules.py` — typed timestamp-unit
  contract alignment.
