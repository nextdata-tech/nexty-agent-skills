---
id: 2026-09-21-source-contract-hardening
date: 2026-09-21
label: "nxd-generate-data-product: harden copied source and ratio contracts"
plugin_version: 0.51.5
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — harden copied source and ratio contracts

## Notes

This change hardens a newly introduced source-contract recipe; no pre-change
scenario arm exists for a controlled before/after comparison. The live B3 run
that motivated the recipe was not a qualified benchmark arm, so manufacturing a
score would make the evidence less trustworthy. This remains an acceptance-only
`NO_EVAL` entry.

The recipe now supports an explicit output quantum for fractional ratios while
preserving integer cent-scaled CPA behavior, rejects blank required fields,
reports missing row-ratio inputs through the typed contract error, and documents
the timing and policy boundaries of coverage and zero-denominator checks.

## Evidence

- `evals/tests/test_source_contract.py` — fractional quantum, blank-field,
  missing-row-field, aggregate-ratio, row-ratio, and copied-recipe checks.
- `evals/tests/test_skill_scripts_are_installable.py` — direct-install and
  archive-presence checks for the copied recipe.
- `scripts/validate_skills.py` — skill contract and synchronized-version check.
