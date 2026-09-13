---
id: 2026-09-10-shared-semantic-intent-foundation
date: 2026-09-10
label: "shared semantic intent foundation and query-adapter packaging"
plugin_version: 0.50.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — shared semantic intent foundation and query-adapter packaging

## Notes

The query adapter's four-part intent gate is extracted into a shared
foundation, and the Desktop adapter now carries the same strengthened contract:
complete agreed-catalog coverage, a catalog-aware critic, a round-trip echo,
and clarification or abstention for ambiguity. The affected semantic MCP and
Desktop supervisor scenarios are explicitly `ci_skip` and require separately
provisioned runtimes, so no trustworthy before/after arm is available in this
checkout. This is therefore an honest `NO_EVAL`, not a claim that the contract
is behaviorally unchanged. The changed installer, archive, scenario-selection,
and adapter-contract boundaries are covered by deterministic tests instead.

## Evidence

- `evals/tests/test_semantic_intent_coverage.py` covers the shared four-part
  gate, adapter boundaries, and affected-scenario declarations.
- `evals/tests/test_skill_scripts_are_installable.py` covers explicit adapter
  dependency retention, standalone archive closure, and install lifecycle.
- `scripts/validate_skills.py` and `scripts/validate_archives.py` cover source
  and release-archive closure.
