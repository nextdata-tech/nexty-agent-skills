---
id: 2026-09-10-workflow-v2-zero-row-live-attempt
date: 2026-09-10
label: "workflow-v2: official zero-row live attempt"
plugin_version: 0.49.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — workflow-v2: official zero-row live attempt

## Notes

No valid benchmark arm can be recorded for this attempt. The official
Sonnet-medium `zero-row-optional-output` run completed as an automatic zero
after the configured desktop-Python checkout was deleted during the run, so
trusted validation and admission could not complete. The run is retained as
diagnostic evidence only; it is not a skill PASS or FAIL and there is no
like-for-like before/after pair. Manufacturing a measured result from it would
misrepresent an environment failure as a skill signal.

## Evidence

- `evals/tests/test_workflow_v2_job_loop_contract.py` — the documented
  workflow-v2 handoff, review-attestation paths, and action ordering.
- `evals/dp-scenarios/tests/test_run_local_claude.py` — live-run environment
  and installed-pack version plumbing.
- `evals/dp-scenarios/tests/test_runner_environment.py` — host-runtime and
  runner environment contract.
- `evals/dp-scenarios/tests/test_grading_gates.py` — nested workflow
  attestation pairing and construction grading contract.
