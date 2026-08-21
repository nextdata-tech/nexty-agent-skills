---
id: 2026-08-21-field-mapper-contract-drift
date: 2026-08-21
label: "nxd-generate-data-product: field-mapper contract drift against the installed harness"
plugin_version: 0.38.2
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-generate-data-product: field-mapper contract drift

## Notes

No public scenario builds a closure that maps from inside its transform. The
mapper scenarios in the suite exercise consent-gate refusals with fixtures, not
a live provider dispatch, so none of the four defects below can appear in them:
each one fires only when generated code actually calls `make_call` and
`map_inputs` against the installed harness with a real grant.

All four were found in one live build — a closure that judges open Linear
tickets in-transform under a user-authored grant — and each failed in a way
that pointed away from the documentation:

- `Grant.check(spec, inputs)` as documented raises `TypeError` before any
  dispatch. The installed signature is keyword-only `input_fields` /
  `document_classes`.
- `make_call` is documented with `allow_env=True`; it defaults to **False**.
  A closure that follows the docs and omits it fails with `credential_missing`
  for a credential that is present in the child's environment.
- `spec-id` prints the id of the **bound** spec — load, compile the wire schema
  in, stamp `harness_version` — while `MapperSpec.load(p).mapper_spec_id`
  reports a different one. Any check comparing a correctly-authored grant
  against an unbound spec refuses it as `spec_mismatch`, inventing a consent
  failure. Declaring `harness_version` in the spec file does not fix it; it
  moves the id again.
- `target_row_key` is a content-derived hash and nothing the harness returns —
  not `MapperProposal`, not `MapperEvidence`, not `Resolution` — carries the
  input identity back. `target_row_key_for_input` is therefore not optional for
  a caller, yet it was absent from the documented public surface. Treating the
  row key as the business key made every downstream assert reject every row for
  belonging to an entity that does not exist.

Manufacturing a scenario for these would mean standing up a paid provider
dispatch in CI, which the suite deliberately does not do.

## Evidence

`evals/tests/test_field_mapper_contract_drift.py`, ten tests in two halves.

Six assert the documentation and run everywhere, including in CI, which has no
`nxd` wheel; all six were verified to fail against the previous revisions of
`mapper/CONTRACT.md` and `reference/field-mapper.md`. Four use the installed
package as the signature oracle and skip where it is absent — deliberately not
`importorskip` at module scope, so the doc half cannot vanish silently with it.

Every one of the four corrections has at least one **ungated** carrier. An
earlier revision gated the `Grant.check` doc assertions behind the oracle skip,
which left that correction unverified anywhere CI could see it — the failure
mode this split exists to prevent.

The oracle half is what keeps this from drifting again: if a future release
changes `Grant.check`, the `allow_env` default, or starts returning identity on
a record, those tests fail and the docs get re-derived rather than quietly
going stale a second time.
