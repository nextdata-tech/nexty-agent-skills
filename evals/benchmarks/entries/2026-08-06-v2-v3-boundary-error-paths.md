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
exception type that escaped its handler, a flag that was accepted and ignored,
and the diagnostic vocabulary those paths report under. None is reachable from
an agent transcript, so no public scenario arm can distinguish the fix — a
scenario manufactured to reach a v2 lock holding a malformed v3 snapshot would
measure the fixture, not the skill.

The defects arrived with the version dispatch added in #159.
`dp_diagnostics.canonical_object` routes on the sniffed `dp_spec_version`, so v2
call sites can raise `dp_spec_authoring.ParseError` — a `ValueError`, not the
`SpecReadError` the v2 lock verifier caught. The verifier exited without a
report, leaving a form-facing consumer nothing to render. Separately,
`validate_dp_spec.py` accepted `--proposal` against a v2 spec and never read it,
returning `ok: true` for an unchecked proposal; `dp_diagnostics.write_lock` had
the same arm at the higher-stakes site, since it is the command that writes the
binding, while its v3 counterpart already required the proposal.

Four changes fix those three defects, and two more keep them from recurring or
being misread:

1. The v2 lock verifier's snapshot and live-spec canonicalization both return a
   diagnostic instead of raising.
2. `validate_dp_spec` rejects `--proposal` against a v2 spec, after the parse so
   an unreadable source still reports why it cannot be read.
3. `write_lock` rejects the same flag on the same grounds.
4. `canonical_object` normalizes the v3 parse failure into `SpecReadError`, its
   single documented failure type. Prophylactic rather than a live fix — the CLI
   catches the wider `_READ_FAILURES` — but without it the next caller that
   reasonably catches `SpecReadError` reintroduces the escape.
5. Vocabulary: `spec.proposal.unsupported` and `closure.live_spec_unparseable`
   are registered, so one user mistake reports one code *and one path* across
   both commands, and both lock generations answer a live spec they cannot read
   identically. Previously `write_lock` reported `pin.spec_compile_error` ("the
   supervisor could not compile the spec") for a wrong flag, and the two
   generations disagreed, neither matching its registry summary. The v2
   verifier's `is_file()` pre-check is gone with them: it answered a missing
   live spec with `closure.spec_snapshot_missing` addressed at the closure
   snapshot, a file that is present and intact, where v3 let the read raise and
   reported the live-spec fault. Letting the read raise in both places makes the
   missing and the unparseable case agree across generations.
6. The `spec.` table's header claimed a bidirectional invariant that
   `test_validator_code_coverage.py` does not enforce — it exercises the `v2.*`
   vocabulary — which is why nothing noticed that `spec.parse.invalid` and
   `spec.frontmatter.unsupported_version` are emitted without being registered.
   The comment now states what actually runs.

## Evidence

`evals/tests/test_dp_spec_authoring.py` carries the change. Nine tests fail
against the pre-#164 implementation and pass after it, covering every arm above:

- `test_v2_lock_verify_reports_an_unparseable_v3_snapshot_instead_of_raising`
  and `test_v2_lock_verify_reports_an_unparseable_v3_live_spec_instead_of_raising`
  — unhandled `ParseError` in place of a report (arm 1).
- `test_validate_dp_spec_rejects_a_proposal_supplied_against_a_v2_spec`,
  `test_the_rejected_proposal_message_names_only_a_parsed_version`, and
  `test_lock_write_rejects_a_proposal_supplied_against_a_v2_spec` — `ok: true`
  for a proposal that was never opened (arms 2 and 3).
- `test_proposal_rejection_never_masks_the_reason_a_spec_cannot_be_read`,
  parametrized over a v1, a headerless, and a broken-frontmatter source — the
  rejection ran before the parse, so an unreadable document was answered with a
  flag-usage complaint naming a version it never declared (arm 2).
- `test_canonical_object_raises_only_spec_read_error_for_a_bad_v3_source` — the
  only cover for the normalization; before it, `_v3.ParseError` propagated and
  `pytest.raises(SpecReadError)` fails (arm 4).
- `test_one_user_mistake_reports_one_code_across_both_commands`,
  `test_both_lock_generations_report_one_code_for_an_uncanonicalizable_live_spec`,
  and `test_both_lock_generations_report_one_code_for_a_missing_live_spec` — all
  three build real closures and assert the shared code, stage, and path (arm 5).

Three further tests pass against both implementations and hold the fixes to
their scope: `test_v2_lock_verify_still_crashes_on_nothing_for_a_well_formed_closure`
and `test_validate_dp_spec_still_accepts_a_v2_spec_without_a_proposal` guard the
widened `except` against swallowing the hash comparison it wraps, and
`test_lock_write_still_writes_a_v2_lock_without_a_proposal` keeps the ordinary
v2 pin path writing both closure artifacts. The registry additions are pinned by
`FROZEN_CODES` in `evals/tests/test_dp_diagnostics_schema.py`, which failed until
both codes were added deliberately.
