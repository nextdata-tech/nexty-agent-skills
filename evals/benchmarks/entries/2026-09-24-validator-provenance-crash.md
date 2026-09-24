---
id: 2026-09-24-validator-provenance-crash
date: 2026-09-24
label: "trusted proposal validator reports object-valued provenance instead of crashing"
plugin_version: 0.52.3
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — trusted proposal validator reports object-valued provenance instead of crashing

## Notes

A live B3 `marketing-attribution` Sonnet run wrote `provenance` values as
objects (`{"kind": "explicit"}`). `_validate_default_term_echo` tested set
membership on that value and raised `TypeError`, so the supervisor-embedded
validator exited 1 with no report. The supervisor could relay only the opaque
`typed proposal failed trusted validation`. The shell-less agent retried the same
blind error until the turn timed out. The fix turns the value into the existing
`v3.term.priority_provenance` issue. `_validate_provenance` already reported
`v3.provenance.value`, so the agent now gets a structured, actionable issue.

No scenario isolates this: whether it triggers depends on the agent's first
proposal shape. The deterministic test carries the evidence. It reproduces the
crash on the previous implementation.

## Evidence

- `evals/tests/test_dp_spec_authoring.py` —
  `test_object_valued_provenance_is_an_issue_not_a_crash` raises `TypeError`
  against the previous `dp_spec_authoring.py` and passes with the guard.
