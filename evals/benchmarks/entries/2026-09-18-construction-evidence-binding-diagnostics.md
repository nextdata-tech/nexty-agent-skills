---
id: 2026-09-18-construction-evidence-binding-diagnostics
date: 2026-09-18
label: "distinguish observed construction evidence from an unpublished build"
plugin_version: 0.51.3
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — distinguish observed construction evidence from an unpublished build

## Notes

No public scenario can distinguish this harness-only diagnostic refinement by
score: construction must still fail when the supervisor publishes no release.
The change prevents the report from calling a successful pre-publication
`check_data_product` or completed reviewer dispatch "not observed". It emits
`construction_published_build_missing` instead, while retaining the original
absence findings when either call is genuinely missing. This complements the
earlier construction-gate contract entry; it does not relax the publication
binding required for a passing construction gate.

## Evidence

- `evals/dp-scenarios/tests/test_grading_gates.py` — a structured successful
  self-check and canonical inline reviewer result with no published build
  fail only through `construction_published_build_missing`, while the quiet
  transcript still reports missing observations.
- `evals/dp-scenarios/tests/test_runner_tier.py` — a malformed published
  identity reports the observed reviewer dispatch plus the missing-release
  diagnostic rather than a false reviewer-absence finding.
