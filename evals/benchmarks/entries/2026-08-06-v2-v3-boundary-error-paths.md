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

All three defects were introduced by the version dispatch added in #159:
`dp_diagnostics.canonical_object` now routes on the sniffed `dp_spec_version`,
so v2 call sites can raise `dp_spec_authoring.ParseError` — a `ValueError`, not
the `SpecReadError` the v2 lock verifier caught. The verifier exited without a
report, leaving a form-facing consumer nothing to render. Separately,
`validate_dp_spec.py` accepted `--proposal` against a v2 spec and never read it,
returning `ok: true` for an unchecked proposal on the one boundary whose purpose
is binding approvals to proposal hashes. `dp_diagnostics.write_lock` had the
same "accepted and ignored" arm at the higher-stakes site — it is the command
that writes the binding — while its v3 counterpart already required the
proposal, leaving the boundary asymmetric.

## Evidence

`evals/tests/test_dp_spec_authoring.py` carries the fix. These tests were each
verified to fail against the previous implementation and to pass after it:

- `test_v2_lock_verify_reports_an_unparseable_v3_snapshot_instead_of_raising`
  and `test_v2_lock_verify_reports_an_unparseable_v3_live_spec_instead_of_raising`
  — unhandled `ParseError` in place of a report.
- `test_validate_dp_spec_rejects_a_proposal_supplied_against_a_v2_spec` and
  `test_lock_write_rejects_a_proposal_supplied_against_a_v2_spec` — `ok: true`
  for a proposal that was never opened.
- `test_proposal_rejection_never_masks_the_reason_a_spec_cannot_be_read`
  — the rejection ran before the parse, so an unparseable or v1 source was
  answered with a flag-usage complaint naming a version it never declared.

Three further tests pass against both implementations and hold the fixes to
their scope: `test_v2_lock_verify_still_crashes_on_nothing_for_a_well_formed_closure`
and `test_validate_dp_spec_still_accepts_a_v2_spec_without_a_proposal` guard the
widened `except` against swallowing the hash comparison it wraps, and
`test_lock_write_still_writes_a_v2_lock_without_a_proposal` keeps the ordinary
v2 pin path writing both closure artifacts.
