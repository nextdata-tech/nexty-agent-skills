---
id: 2026-09-09-workflow-v2-construction-contract
date: 2026-09-09
label: "supervisor v2 admission path in the job loop and generator"
plugin_version: 0.48.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — supervisor v2 construction contract

## Notes

No existing public scenario can distinguish this change. The available live
construction scenarios exercise the legacy `build_data_product` surface and do
not expose the supervisor v2 workflow API (`get_workflow_capabilities`,
`prepare_workflow`, `advance_workflow`, and admitted `start_run`) to the agent.
Running those scenarios would measure a different contract rather than this
skill change. The change is therefore pinned by deterministic static ordering,
no-legacy, review-relay, admission, and reset tests.

## Evidence

- `evals/tests/test_workflow_v2_job_loop_contract.py` — thirteen deterministic tests
  over the shipped skill/reference text.
- `src/nxd-run-job-loop/reference/workflow-v2.md` — the v2 construction
  sequence and bounded review-report contract.
