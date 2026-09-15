---
id: 2026-09-14-supervisor-admission-only-skills
date: 2026-09-14
label: "remove retired supervisor construction fallbacks from skills"
plugin_version: 0.49.4
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — supervisor admission-only skill guidance

## Notes

No existing public scenario can distinguish this change. The merged supervisor
now exposes workflow-v2 admission as the only construction path, while the
available live scenarios still target the retired one-shot construction and
validation surfaces. Running them would measure an incompatible API contract,
not this skill-pack cleanup. The change is therefore pinned by deterministic
contract tests over the installed skill references and by the package
validation/build checks.

## Evidence

- `evals/tests/test_workflow_v2_job_loop_contract.py` — removed construction
  tools are absent from reachable installed references and v2 ordering remains
  explicit.
- `evals/tests/test_resume_first_gate.py` — resume-first recovery is followed
  by workflow-v2 reconstruction only when the published artifact is gone.
- `src/nxd-run-job-loop/reference/workflow-v2.md` — the supervisor-owned
  admission sequence and action boundary.
