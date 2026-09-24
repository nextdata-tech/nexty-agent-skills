---
id: 2026-09-23-trace-and-driver-guidance-review-fixes
date: 2026-09-23
label: "fix MCP trace duplication and restore driver guidance"
plugin_version: 0.52.4
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — fix duplicate MCP trace requests and restore exact driver guidance

## Notes

No scenario isolates the proxy's exactly-once request trace contract. A desktop
build can exercise the three exact local driver IDs, but its result cannot
isolate that instruction from other agent and supervisor behavior. This
follow-up restores the fixed IDs that were present in the pre-merge mainline,
clarifies the API probe sentence while preserving the remaining companion
requirements, and adds deterministic tests for forwarded and synthetic trace
cardinality, response correlation, and the skill/reference driver mapping.

## Evidence

- `evals/tests/test_desktop_stdio.py` — asserts exactly one request trace record
  for each of two forwarded requests; the runner-owned reader logs one safe
  summary per call, correlates synthetic responses, and omits raw arguments and
  response text from the trace.
- `evals/tests/test_source_contract.py` — checks each service-to-driver mapping
  against `reference/infra-profile.md`, pins the no-shortening instruction, and
  protects the API companion/probe wording.
