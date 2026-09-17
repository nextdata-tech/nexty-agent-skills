---
id: 2026-09-17-workflow-v2-review-handoff-hardening
date: 2026-09-17
label: "harden workflow-v2 review handoff and contract evidence"
plugin_version: 0.51.1
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
typed timestamp contract corrections shipped with the same pack revision. The
runner now creates only mode-0700 `captures/` and `blueprints/` roots for an
in-scope supervisor data directory, including when that directory is the run
root; lifecycle and direct-helper tests cover this boundary. The workflow-v2
guidance now has a complete copyable closed-v3 payload example, an explicitly
non-copyable abbreviated request envelope, and contract tests that compare the
documented keys, decision statuses, delivery object, and compiled source shapes
with the canonical authoring schema.

## Evidence

- `evals/dp-scenarios/tests/test_runner_review_guard.py` — documented
  workflow-v2 review-input shape, arbitrary retention layouts, stale-state
  clearing, path containment, and finalization cutoff.
- `evals/dp-scenarios/tests/test_runner_claude_adapter.py` — early data-dir
  failure and runner-owned review-root wiring.
- `evals/dp-scenarios/src/dp_scenarios/runner/environment.py` and
  `evals/dp-scenarios/tests/test_runner_environment.py` — mode-0700 retained
  roots, external-path no-op, data-dir/run-root equality, and `prepare()`
  lifecycle invocation.
- `evals/tests/test_workflow_v2_job_loop_contract.py` — split skill/reference
  guidance checks and canonical-or-exact closed-v3 structure assertions.
- `src/nxd-run-job-loop/SKILL.md` and
  `src/nxd-run-job-loop/reference/workflow-v2.md` — the compact closed-v3
  reminder plus the complete payload and non-copyable envelope examples.
- `evals/tests/test_review_closure_scope_contract.py` — structural notes are
  not promoted to consumer-impact claims.
- `evals/tests/test_spec_api_compiler_rules.py` — typed timestamp-unit
  contract alignment.
