---
id: 2026-09-24-review-sweep-siblings
date: 2026-09-24
label: "review-closure sweeps each defect class across all siblings in one round"
plugin_version: 0.52.5
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — review-closure sweeps each defect class across all siblings in one round

## Notes

A live B3 `marketing-attribution` Sonnet run on 2026-09-24 needed three review
rounds. Round 0 flagged one promise verifier for "assert theatre": it did not
independently re-derive what it checked. Round 1 then flagged two sibling
verifiers that had the same gap in the round-0 capture. Each round costs the
owner a reset, a recapture, and a fresh review. The B1 `crm-pipeline` run showed
the same churn: seven consent → capture → review cycles. The reviewer now
checks every assert and promise verifier and sweeps siblings of any defect class
within the round.

No public eval harness scenario in `evals/run.py` isolates review round count.
The dp-scenarios live runs that do are local-only, nondeterministic, and
costly, and the B-series harness was still changing at the same time, so a
paired measured record would not isolate this edit. The live B3 rerun remains
the qualification check. Deterministic evidence pins the guidance.

## Evidence

- `evals/tests/test_source_contract.py` —
  `test_review_closure_sweeps_each_defect_class_in_one_round` pins the sweep
  section and the all-verifiers instruction; it fails against the previous
  `SKILL.md`.
