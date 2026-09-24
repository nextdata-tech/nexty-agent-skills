---
id: 2026-09-24-validation-failure-facts
date: 2026-09-24
label: "repair reported failed contracts and exception class first"
plugin_version: 0.52.9
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — repair reported failed contracts and exception class first

## Notes

A live B1 `crm-pipeline` Sonnet run on 2026-09-24 failed trusted validation
five times with `validation/scratch_transform_failed` and never published. The
supervisor knew the cause (a `decimal.ConversionSyntax` in the transform, then
four failed contracts) but reported only an HTTP 500, and
`check_data_product`, which does not execute against the live source, passed
every time. nextdata-tech/nxd#7959 adds bounded `failed_contracts` and
`exception_class` to the failure diagnostic and to `inspect_run`. The "When
validation fails" section of `workflow-v2.md` now tells the agent to repair
those first and explains why `check_data_product` can pass meanwhile.

No public `evals/run.py` scenario isolates this. The B1 live rerun on a
supervisor with nxd#7959 is the qualification check.

## Evidence

- `evals/tests/test_source_contract.py` —
  `test_validation_failure_facts_are_repaired_first` pins the rule; it fails
  against the previous `workflow-v2.md`.
