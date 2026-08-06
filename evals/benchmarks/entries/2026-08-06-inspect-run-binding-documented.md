---
id: 2026-08-06-inspect-run-binding-documented
date: 2026-08-06
label: "nxd-run-job-loop: correct the build record's stale inspect_run unbound claim"
plugin_version: 0.36.1
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-run-job-loop: correct the build record's stale inspect_run unbound claim

## Notes

Documentation-of-record only: no agent behavior changes. The loop already called
`mcp__nxd-desktop__inspect_run` once with the failed `run_id` and classified from
that diagnostic — `SKILL.md` and `reference/failure-handling.md` have carried the
bound contract since the call-shape work. What lagged was
`reference/build-record.md`, which still described the tool as having no producer:
"The pack names a run-inspection tool once and never uses it — no schema, no
reference doc, no step, no test." Every clause of that was false, and its
`supervisor_detail` JSON example still showed `origin: "unbound"`.

No scenario can distinguish this change, because no scenario observes it. The
prose describes a binding that already existed in the arm both before and after,
so an eval run would return the identical transcript on either side.
Manufacturing a scenario to produce a number here would measure the loop's
existing use of `inspect_run`, not this correction to the doc.

The limits were deliberately preserved rather than declared closed: stage
attribution remains an agent inference (the supervisor emits no
`code`/`stage`/`severity`/`owner`), `s5_serve` stays indistinguishable from
`s4_pin`/`s6_run`/`s7_publish`, and per-attempt supervisor identity is still
genuinely `origin: "unbound"` — so that row of the origin vocabulary table stays
valid.

## Evidence

`evals/tests/test_build_record_schema.py` pins the build-record schema and the
`origin` vocabulary the corrected example must satisfy, including
`supervisor_detail` carrying a verbatim supervisor-authored payload;
`evals/tests/test_dp_diagnostics_schema.py` pins the diagnostic contract that
`origin: supervisor_reported` must meet, and
`evals/tests/test_build_record_s0_producer.py` covers producer binding. All 104
tests across the three files pass with the corrected example.
