---
id: 2026-08-15-nex-877-provider-adapter-contract
date: 2026-08-15
label: "NEX-877: public field-mapper provider adapter contract"
plugin_version: 0.37.2
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — NEX-877: public field-mapper provider adapter contract

## Notes

No public skill scenario can distinguish this change: the adapter executes in
the `nxd` monorepo runtime, while this repository's eval runner does not create
a Desktop transform or make provider calls. Manufacturing a live scenario here
would measure provider availability and spend rather than the documented
contract. The six-record synthetic Desktop publication/query run remains an
explicit acceptance test for the runtime issue, not a skill-pack benchmark.

## Evidence

The carrying static contract test checks the public `make_call` signature,
credential precedence and opt-out, parsed-response/error wording, and that the
E2E example uses `make_call` without importing the SDK or private transport:
`evals/tests/test_mapper_supervisor_approval_contract.py`.
