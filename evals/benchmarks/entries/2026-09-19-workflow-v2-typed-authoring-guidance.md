---
id: 2026-09-19-workflow-v2-typed-authoring-guidance
date: 2026-09-19
label: "workflow-v2: pin empty open questions and typed transform operations"
plugin_version: 0.51.3
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — workflow-v2 typed authoring guidance

## Notes

No public eval scenario can distinguish these narrow authoring-guidance
clarifications in a valid before/after arm. The change makes the existing v3
contract explicit in the workflow reference: an empty Open Questions section
maps to an empty typed list with no empty source-map entry, platform-fixed P3
defaults must be stated in the echo, and API fetching/pagination remains
connector behavior rather than a typed transform operation. Running a broader
workflow scenario would measure unrelated construction, provider, and grading
behavior, so it would manufacture evidence for this documentation-only
correction.

## Evidence

- `src/nxd-run-job-loop/reference/workflow-v2.md` — live shipped workflow
  reference containing the empty-list and exact transform-operation guidance.
- `evals/tests/test_workflow_v2_job_loop_contract.py` — existing carrying test
  that derives the allowed operation enum from `dp_spec_authoring.py` and pins
  the reference guidance.
