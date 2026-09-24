---
id: 2026-09-24-independent-promise-verifiers
date: 2026-09-24
label: "independent promise verifiers and one-round defect-class review sweeps"
plugin_version: 0.52.5
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — independent promise verifiers and one-round defect-class review sweeps

## Notes

The live B3 `marketing-attribution` Sonnet run on 2026-09-24 got through
prepare, consent, capture and review, then spent its turn budget on review
churn. Each fresh review round found one more promise verifier that only
checked a row against its own columns. B1 `crm-pipeline` showed the same
pattern: seven consent → capture → review cycles. The generator guidance now
requires one independent verifier per promised output. The reviewer now sweeps
a whole defect class in one pass.

No scenario in the public `evals/run.py` harness isolates review round count.
The dp-scenarios live runs that do are local-only, nondeterministic and costly.
The B-series harness was also changing in the same window, so a paired record
would not isolate this edit. The live B3 rerun remains the qualification check.
Deterministic evidence pins the guidance.

## Evidence

- `evals/tests/test_source_contract.py` —
  `test_promise_verifiers_are_independent_and_review_sweeps_defect_classes`
  pins the independent-verifier rule and the defect-class sweep; it fails
  against the previous skill files.
