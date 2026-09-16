---
id: 2026-09-16-reviewer-deadline-guidance
date: 2026-09-16
label: "surface and budget the retained-capture reviewer deadline"
plugin_version: 0.49.6
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — surface and budget the retained-capture reviewer deadline

## Notes

No public scenario isolates reviewer prompt comprehension from provider timing,
closure complexity, and the runner's enforced deadline. The latest B1 run
ended `ungraded` when its retained-capture reviewer exceeded the existing
120-second bound; it did not provide a controlled before/after arm for this
guidance change. A numeric benchmark would therefore conflate prompt
comprehension with model/runtime variance.

The reviewer skill and workflow-v2 dispatch now make the caller-supplied hard
budget explicit, prioritize high-value checks, reserve time for a terminal
claims response, and permit one informational progress checkpoint without
extending the absolute deadline.

## Evidence

- `evals/tests/test_workflow_v2_job_loop_contract.py` — the canonical reviewer
  dispatch carries the budget and bounded-progress instructions.
- `evals/dp-scenarios/tests/test_runner_environment.py` — the scenario contract
  exposes the same budget and preserves the non-extending deadline semantics.
- `src/nxd-review-closure/SKILL.md` — the reviewer’s prioritized, partial-result
  behavior.
