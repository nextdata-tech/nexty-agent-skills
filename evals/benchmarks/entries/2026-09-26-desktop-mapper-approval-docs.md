---
id: 2026-09-26-desktop-mapper-approval-docs
date: 2026-09-26
label: "document the workflow-v2 mapper approval and cover both supervisor grant paths"
plugin_version: 0.54.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — document the workflow-v2 mapper approval and cover both supervisor grant paths

## Notes

WP14 of the Desktop workflow-v2 mapper admission design. It documents the
runtime that shipped on nxd main in WP0-WP11: the `mapper-confirmation-v1`
formal-approval handler, the strict grant, the OS-dialog approval, every mapper
call through the broker with the key in the Keychain, the MAC-checked durable
ledger, stub-backed validation and the inspection projection. WP12 (an
activation bundle registering the requirement) and WP13 (a headless eval) were
not implemented. The docs therefore say that the bundled Desktop activation
stops a mapper closure at `validation/mapper_closure_unsupported`, and that
mapper builds run only on macOS. This change covers:

- `field-mapper.md` § Desktop supervisor approval boundary replaces the
  "unsupported / future handler" text with the shipped flow, the strict grant,
  the grant refusal codes, D1 (declared fields are reviewed, not enforced) and
  D4 (scratch contracts on mapper outputs are advisory).
- `workflow-v2.md` gains § Mapper approval with a fail-closed recovery table for
  every approval, validation and run code.
- `nxd-review-closure` gains a grant-scope check that flags fields sent but
  not declared.
- Phase G now reports `grant.ambiguous_path` (error) when both supervisor grant
  paths exist and `grant.not_at_supervisor_path` (warning) when consent is
  complete but the files are not at the paths the supervisor reads.

No public `evals/run.py` scenario can exercise this. The approval needs the
supervisor's OS dialog and a workflow contract that registers the mapper
requirement. The bundled activation does not register it, and the headless nxd
eval planned as WP13 was never built. Every documented code was checked against
nxd main source instead.

## Evidence

- `evals/tests/test_grant_gate_phase_g.py` —
  `test_both_supervisor_grant_paths_fail`,
  `test_both_paths_fail_even_when_the_second_is_malformed`,
  `test_grant_off_the_supervisor_paths_warns` and
  `test_spec_off_the_supervisor_path_warns` fail against the previous
  `self_check.py`. `test_either_supervisor_grant_path_passes_clean` guards both
  accepted paths against a false warning.
- `evals/tests/test_mapper_supervisor_approval_contract.py` —
  `test_desktop_mapper_flow_is_the_shipped_workflow_v2_requirement`,
  `test_declared_data_scope_is_never_described_as_enforced`,
  `test_scratch_contracts_on_mapper_outputs_are_advisory` and
  `test_workflow_recovery_table_fails_closed` fail against the previous docs.
  `test_workflow_docs_match_the_shipped_supervisor_codes` fails against the
  first draft of this change, which documented codes nxd never emits
  (`workflow/mapper_ledger_revoked`, `workflow/mapper_provider_unavailable`)
  and omitted the `mapper_grant_refused` and `mapper_integrity` run codes.
