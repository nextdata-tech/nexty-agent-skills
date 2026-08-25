---
id: 2026-08-25-self-check-shift-left-gates
date: 2026-08-25
label: "nxd-run-job-loop: three self-check gates that shift a silent failure left"
plugin_version: 0.39.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-run-job-loop: three self-check gates that shift a silent failure left

## Notes

No public scenario builds an `api-source` closure and then queries it, so no
scenario can distinguish this change. `job-loop-serve-query-refine` and
`job-loop-export-handoff` both require a live desktop supervisor and are
`ci_skip`; neither exercises a credentialed connector's offline self-check, and
none of the runnable scenarios promises a model with no semantic view.
Manufacturing a scenario to produce a figure would make the evidence less
trustworthy, not more, which is why this entry carries no arm.

All three gates were found by a **cleanroom reproduction**: rebuilding a data
product from `dp-blueprint.md` alone, reading no part of the existing closure,
against the criterion that all *logic* needed to reproduce a product is
encapsulated in the blueprint while identity and approval are re-handled by the
new holder. Each cost either a wrong answer or a whole closure before anything
reported it.

**`runtime.dry_run_not_runnable` (info).** A `db-source`/`api-source` closure
reads its connection out of `secrets`, which the offline harness cannot supply,
so Phase B raises `KeyError` before the transform does anything.
`reference/api-source.md` already documented that as expected and told the author
not to code around it with a profile-reading fallback. What it did not say — and
what this fixes — is that failing Phase B also skips Phases C, D and E, the
closure-record, policy-boundary and reach-gate checks. In the cleanroom run those
three were lost to that expected `KeyError`, and running them by hand is what
found a `spec.py` wiring zero of seventeen approved contracts and a
`needs_review` verdict that was both landed as data and hardcoded in the
transform. Phase B now reports NOT RUNNABLE, marks `s2_transform` `skipped`
rather than `passed`, and continues. The waiver is keyed on the declared
connector, not on the exception type: a CSV closure with a genuinely missing
secret still fails Phase B.

**`closure.contract_phase_unsupported` (error, owner `user`).** An Input's
Expectations compile to `pre_transform` contracts, and this runtime executes a
custom input expectation only for a declared CSV source-aligned input. An
`api-source` closure declares none, so the approved inventory can never be
satisfied. The only symptom was a bare `contract_inventory_mismatch` after a
whole closure existed — and the obvious way to clear that is to wire the
expectations as output promises, which silently moves a phase the user approved.
The new code names the offending ids, names the three resolutions, and says all
three are spec edits needing re-approval. It is `owner: user` for that reason: an
agent cannot re-phase an approved contract on its own.

**`struct.model_not_queryable` (warning), plus the join half of
`struct.key_not_groupable`.** `run_semantic_query` requires at least one measure,
so a promised model backing no `semantic_view` cannot be selected at all — its
rows are reachable only through another model's metric across a join, where a
filter scopes that model's aggregate rather than this model's spine and quietly
returns every row. The cleanroom product hit exactly that: `ticket_signals` was
landed, described and promised, and the question "on what evidence" could not be
answered until a `COUNT` view and a groupable dimension were added. A field
carrying only `join(...)` is the same defect as a bare `primary_key()` and now
rides the existing warning.

Run against the cleanroom closure, the new checks immediately reported two
defects that build had already shipped: a join-only foreign key on
`pocket_comments_landed`, and four promised models — including `priority_rubric`
and `priority_bands`, which that blueprint's Outputs explicitly promise anyone
can read — reachable by no metric.

`nxd-generate-data-product`'s Step 2 gains the matching authoring rule, because
the previous guidance ("metrics stay question-driven") is what argued against
adding the view in the first place. That rule decides *what to aggregate*; the
new one decides *whether the model can be reached at all*.

## Evidence

`evals/tests/test_self_check_queryability_and_phase_gates.py` — twelve tests,
**eight of which fail against the previous implementation**:

- `test_promised_model_backing_no_view_is_flagged`
- `test_join_without_a_dimension_is_flagged`
- `test_missing_secret_is_waived_only_for_a_network_connector`
- `test_the_waiver_is_keyed_on_the_connector_not_the_exception_type`
- `test_phase_b_failure_no_longer_short_circuits_phase_c`
- `test_pre_transform_contracts_on_an_api_source_are_rejected`
- `test_pre_transform_contracts_on_a_csv_source_are_fine`
- `test_no_pre_transform_contracts_is_fine`

Two of the remaining four are negative controls asserting a code does NOT fire,
which is the half that keeps these gates usable: a rule firing on every correct
closure gets deleted rather than obeyed. The other two run the whole script
against a synthetic closure and are skipped where `dlt` is absent — CI installs
neither `dlt` nor `nxd`, so a synthetic transform dies at
`runtime.import_failed` before `ingest()` is ever called.

**That skip costs no coverage**, and arranging for it not to is the reason the
dry-run decision is a named predicate (`dry_run_waived`) rather than an inline
condition. The predicate and the guard placement are asserted by extraction, the
same way `evals/tests/test_reach_gate_phase_e.py` and
`evals/tests/test_grant_gate_phase_g.py` assert theirs, so all eight regression cases run in CI. `nxd` is deliberately not part
of the skip condition: `self_check` installs stub `nxd` modules itself, so `dlt`
is the real discriminator.

`test_phase_b_failure_no_longer_short_circuits_phase_c` carries the regression
the first gate exists for. It asserts the stage closes as `skipped` rather than
`passed`, that every sweep over the dry-run database is guarded, and that the
guard is established before Phase C — so a future edit that lets Phase B swallow
Phases C, D and E fails here rather than degrading into a green run that checked
less than it appears to.

`evals/tests/test_dp_diagnostics_schema.py` and
`evals/tests/test_self_check_diagnostic_vocab.py` carry the three new codes
through `FROZEN_CODES` and the shared registry; both failed on the first run of
this change, which is the drift guard working.
