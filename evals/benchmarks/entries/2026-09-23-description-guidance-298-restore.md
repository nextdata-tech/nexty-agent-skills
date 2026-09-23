---
id: 2026-09-23-description-guidance-298-restore
date: 2026-09-23
label: "restore #298 field-level semantic descriptions"
plugin_version: 0.52.2
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — restore #298 field-level semantic descriptions

## Notes

Documentation and example correction only. No current scenario distinguishes
whether a semantic description is authored on `field()` / `metric_field()` or
inside the role builder; a measured agent run would not isolate this contract
repair. The deterministic source-contract tests pin the placement and ensure
that later documentation edits cannot restore the contradictory role-only rule.

## Evidence

- `evals/tests/test_source_contract.py` — banned stale guidance, checks parsed
  fenced Python examples (with an explicit deprecated-example exemption),
  scans inline spans across soft-wrapped paragraphs/lists/tables, and pins the
  field-level inheritance guidance.
