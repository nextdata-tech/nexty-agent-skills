---
id: 2026-09-04-nxd-run-job-loop-incremental-state
date: 2026-09-04
label: "nxd-run-job-loop: incremental transform state persistence checks"
plugin_version: 0.43.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-run-job-loop: incremental transform state persistence checks

## Notes

No currently runnable PR scenario can distinguish this change. The only
directly relevant public scenario, `incremental-transform-state`, is marked
`ci_skip` because it requires a multi-turn Claude backend, while the PR gate
uses the Codex backend and intentionally skips it. I did not manufacture a
before/after agent run from an unavailable execution tier; this entry records
that there is no comparable benchmark arm.

The change is covered by deterministic tests instead: the self-check now runs
the stateful transform again and verifies that the cursor persists, advances
only after rows land, and keeps row counts stable. A missing persistence write
is surfaced as a specific diagnostic rather than silently passing.

## Evidence

- `evals/tests/test_self_check_queryability_and_phase_gates.py::test_stateful_transform_that_lands_rows_without_state_fails` — carrying regression test for the missing-state-write diagnostic; the test is designed to fail against the pre-change self-check.
- `evals/tests/test_incremental_transform_gate.py` — deterministic coverage for the three-run incremental scenario, state-key trajectory, and current `ci_skip` boundary.
- `python3 evals/benchmark_record.py --check` — benchmark entry and generated index validated in CI.
