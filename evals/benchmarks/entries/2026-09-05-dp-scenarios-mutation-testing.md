---
id: 2026-09-05-dp-scenarios-mutation-testing
date: 2026-09-05
label: "automated mutation testing for the dp-scenarios harness"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — automated mutation testing for the dp-scenarios harness

## Notes

This change is harness tooling and harness tests. It ships a mutmut wrapper
(`evals/dp-scenarios/scripts/mutation_test.py`), its configuration, two CI tiers,
and the property tests that the first mutation run turned up as missing. No
skill under `src/` changes, no scenario changes, and no agent prompt changes, so
no runnable public scenario can distinguish before from after: an agent run
would exercise exactly the same skills against exactly the same fixtures and
produce the same judge checks, turns and tokens either way. Manufacturing a
scenario to attach a number here would make the evidence less trustworthy, not
more.

The measurement that *is* meaningful for this change is the mutation score
itself, and it is recorded in the PR rather than as an eval arm. The first
whole-scope run over `src/dp_scenarios/operator/` and `src/dp_scenarios/grading/`
produced 7930 mutants and a large block of survivors concentrated in the scan
decision tables — 143 in `supported_path_scan` alone, where deleting `httplib2`
from the forbidden import roots or `bash` from the executable tool kinds changed
no test's verdict. `tests/test_grading_scan_tables.py` closes that gap, and the
committed `mutation-baseline.json` is what CI compares against so the count
cannot silently grow again.

## Evidence

- `evals/dp-scenarios/tests/test_grading_scan_tables.py` — 118 property tests
  over the decision tables of `supported_path_scan`, `governed_path_scan`,
  `meaning_preserving_bounding_scan` and `proxy_labelling_scan`. Every case was
  written against a specific surviving mutant and fails if the corresponding
  table entry is removed or renamed.
- `evals/dp-scenarios/tests/conftest.py` and `tests/_repo_paths.py` — the root
  resolution that fixed-parent-hop paths got wrong under a relocated tree; the
  suite could not run at all from `mutants/` before this.
- `evals/dp-scenarios/scripts/mutation_test.py` — the wrapper, its baseline
  comparison, and the survivor explanation output CI publishes.
- `.github/workflows/nightly-mutation.yml` and the `dp-scenarios-mutation` job
  in `.github/workflows/ci.yml` — the two tiers.
