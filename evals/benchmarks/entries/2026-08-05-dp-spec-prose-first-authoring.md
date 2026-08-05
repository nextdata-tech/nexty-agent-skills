---
id: 2026-08-05-dp-spec-prose-first-authoring
date: 2026-08-05
label: "nxd-run-job-loop: prose-first v3 dp-spec authoring boundary"
plugin_version: 0.36.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-run-job-loop: prose-first v3 dp-spec authoring boundary

## Notes

No public scenario exercises the new v3 authoring boundary, typed-proposal
handoff, inline Terms extraction, approval echo coverage, or v3 closure lock
snapshots. Existing scenario arms target the older build workflow and cannot
distinguish this authoring change without manufacturing a new scenario. The
carrying tests below provide deterministic coverage for the new contract.

## Evidence

`evals/tests/test_dp_spec_authoring.py` covers free prose, stable source spans,
inline Terms, Input expectations and Output promises, proposal provenance and
echo coverage, fixed local delivery, decision locks, approval lifecycle, and
v3 lock write/verify snapshots.
