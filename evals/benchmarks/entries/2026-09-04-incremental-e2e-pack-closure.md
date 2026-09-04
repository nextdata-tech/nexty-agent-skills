---
id: 2026-09-04-incremental-e2e-pack-closure
date: 2026-09-04
label: "incremental E2E: named-pack closure and installability boundaries"
plugin_version: 0.44.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — incremental E2E: named-pack closure and installability boundaries

## Notes

No runnable public agent scenario can distinguish these packaging, installer,
documentation, and deterministic-evaluator-contract changes. The relevant
coverage is structural and archive-based, so manufacturing a before/after
agent run would produce an uninformative score rather than evidence for this
change.

## Evidence

- `evals/tests/test_skill_scripts_are_installable.py` — carrying tests for the
  named plugin cache layouts, globally ordered candidates, and complete
  installable archive skill trees.
- `evals/tests/test_api_source_envelope.py` — pins the deterministic envelope
  fact between the checks manifest and its fixture.
- `scripts/validate_skills.py` and `scripts/validate_archives.py` — deterministic
  source and release-archive closure gates exercised by the build and CI.
