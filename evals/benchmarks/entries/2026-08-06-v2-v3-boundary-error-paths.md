---
id: 2026-08-06-v2-v3-boundary-error-paths
date: 2026-08-06
label: "nxd-run-job-loop: v2/v3 cross-generation error paths return diagnostics"
plugin_version: 0.36.1
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-run-job-loop: v2/v3 cross-generation error paths return diagnostics

## Notes

The change is confined to error paths in deterministic helper scripts: an
exception type that escaped its handler, and a flag that was accepted and
ignored. Neither is reachable from an agent transcript, so no public scenario
arm can distinguish the fix — a scenario manufactured to reach a v2 lock
holding a malformed v3 snapshot would measure the fixture, not the skill.

Both defects were introduced by the version dispatch added in #159:
`dp_diagnostics.canonical_object` now routes on the sniffed `dp_spec_version`,
so v2 call sites can raise `dp_spec_authoring.ParseError` — a `ValueError`, not
the `SpecReadError` the v2 lock verifier caught. The verifier exited without a
report, leaving a form-facing consumer nothing to render. Separately,
`validate_dp_spec.py` accepted `--proposal` against a v2 spec and never read it,
returning `ok: true` for an unchecked proposal on the one boundary whose purpose
is binding approvals to proposal hashes.

## Evidence

`evals/tests/test_dp_spec_authoring.py` carries the fix. The three tests
`test_v2_lock_verify_reports_an_unparseable_v3_snapshot_instead_of_raising`,
`test_v2_lock_verify_reports_an_unparseable_v3_live_spec_instead_of_raising`,
and `test_validate_dp_spec_rejects_a_proposal_supplied_against_a_v2_spec` were
each verified to fail against the previous implementation — the first two with
an unhandled `ParseError` in place of a report, the third with `ok: true` — and
to pass after it. Two further tests
(`test_v2_lock_verify_still_crashes_on_nothing_for_a_well_formed_closure`,
`test_validate_dp_spec_still_accepts_a_v2_spec_without_a_proposal`) pass against
both implementations and guard the widened `except` against swallowing the hash
comparison it wraps.
