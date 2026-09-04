---
id: 2026-09-04-nexty-plugin-projections
date: 2026-09-04
label: "nexty plugin projections and local profiler ownership"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nexty plugin projections and local profiler ownership

## Notes

No runnable public agent scenario can distinguish the marketplace projection,
installer marker, profiler ownership, and archive-version changes. A synthetic
before/after agent run would not provide meaningful behavioral evidence.

## Evidence

- `evals/tests/test_skill_scripts_are_installable.py` — deterministic checks for
  projection switching, legacy migration, explicit extras, malformed markers,
  and installable skill trees.
- `evals/tests/test_local_profiler.py` — deterministic checks for the profiler
  now owned and shipped by the semantic-builder skill.
- `scripts/validate_skills.py` and `scripts/validate_archives.py` — source and
  release-archive closure gates.
