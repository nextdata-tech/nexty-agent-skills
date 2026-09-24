---
id: 2026-09-24-advisory-note-proposed-effect
date: 2026-09-24
label: "an advisory review note carries a non-empty proposed_effect"
plugin_version: 0.52.8
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — an advisory review note carries a non-empty proposed_effect

## Notes

`workflow-v2.md` told the agent how to record a LOW advisory claim as an
accepted, not-applied `structural_note`, but did not name `proposed_effect`.
A live B3 `marketing-attribution` Sonnet run on 2026-09-24 published after
such a round and left `proposed_effect` empty. The shipped
`validate_review_round` and the harness construction gate both reject an
empty `proposed_effect`, so the round could not pair with its review, and
construction failed while every other gate passed. The paragraph now names
`applied_files: []` and a non-empty `proposed_effect` that says no closure
change follows. A round in that form passes both validators; the empty form
fails both.

The same "When validation fails" section now tells the agent to repair the
`failed_contracts` and `exception_class` that nxd#7959 adds to a failed
validation diagnostic and to `inspect_run`. A live B1 run retried validation
five times blind because `check_data_product`, which does not execute against
the live source, kept passing.

No public `evals/run.py` scenario isolates this. The B3 live rerun is the
qualification check.

## Evidence

- `evals/tests/test_source_contract.py` —
  `test_advisory_only_review_rounds_report_clear` pins the rule; it fails
  against the previous `workflow-v2.md`.
- `evals/tests/test_source_contract.py` —
  `test_validation_failure_facts_are_repaired_first` pins the failure-facts
  rule; it fails against the previous `workflow-v2.md`.
