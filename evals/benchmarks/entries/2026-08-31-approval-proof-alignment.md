---
id: 2026-08-31-approval-proof-alignment
date: 2026-08-31
label: "supervisor approval transport and mapper review outcome contract"
plugin_version: 0.40.1
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — supervisor approval transport and mapper review outcome contract

## Notes

No public benchmark scenario can distinguish this change without a live Claude
Desktop/Cowork session, a supervisor approval interaction, and a real mapper
review. This patch reconciles shipped skill guidance and examples with the
current supervisor-owned loopback/native-OS approval surface and with the
deterministic `mapper_review_outcomes` publication projection. It does not add
or change a model-facing behavior that an unattended benchmark can measure.

The contract deliberately keeps two proofs separate: the supervisor gate is a
session-local admission decision and is not currently a signed user-identity
receipt, while `ReviewOutcome` proves deterministic publication accounting and
does not authenticate the reviewer. The design remains proposed/partial until
the supervisor issues durable signed approval and execution attestations.

## Evidence

- `evals/tests/test_mapper_supervisor_approval_contract.py` — static contract
  checks for the current approval transport, fail-closed outcomes, unsigned
  boundary, review-outcome accounting, and E2E projection assertions.
- `evals/tests/test_field_mapper_contract_drift.py` — mapper public-contract
  and runtime drift checks.
- `python3 scripts/validate_skills.py --root .` — complete skill-pack
  validation passed after initializing the checked-in examples submodule.
