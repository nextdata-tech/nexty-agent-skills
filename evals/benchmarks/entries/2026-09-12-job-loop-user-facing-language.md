---
id: "2026-09-12-job-loop-user-facing-language"
date: "2026-09-12"
label: "nxd-run-job-loop: user-facing language boundary"
plugin_version: "0.49.3"
status: "NO_EVAL"
scenarios: []
record: null
---
# Benchmark — nxd-run-job-loop: user-facing language boundary

## Notes

The neutral consent scenario was run against clean main and the final pack; both
arms passed all 5 checks. It does not distinguish this prose change because the
pre-change narration rules already covered the tested failure response. The
scenario remains in the public suite as regression coverage, but this entry does
not claim a measured PASS or FAIL for the skill change.

## Evidence

- `evals/tests/test_user_facing_language_contract.py` — carrying assertions for
  the new user-facing language reference and the durable-handoff boundary.

- `evals/public/consent-failure-plain-language/checks.json` — semantic checks
  for approval state, saved-state preservation, one safe next action, and
  sanitized technical explanation.
- `evals/tests/test_workflow_v2_job_loop_contract.py` — existing carrying tests
  for the job-loop's structured handoff and internal-record boundaries.

The consent scenario remains in the public suite as regression coverage, but it
is intentionally not listed as a measured scenario for this `NO_EVAL` entry.
