---
id: 2026-09-12-workflow-v2-proposal-evidence
date: 2026-09-12
label: "workflow-v2: bind proposal-file evidence to preparation"
plugin_version: 0.49.3
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — workflow-v2 proposal-file evidence

## Notes

No public scenario can distinguish this evaluator contract change in a valid
like-for-like benchmark arm. The live B-series workflow exercises the
supervisor admission path, but it does not isolate proposal-file path/content
binding from the other workflow-v2 and construction requirements. Recording a
score from that run would attribute environment and agent-workflow outcomes to
this narrow gate change.

The gate now requires the observed `dp-blueprint.proposal.json` to be beside
the prepared blueprint and to have the same typed-proposal value sent inline.
Because `files_touched` is an end-of-turn snapshot, evidence on the prepare
turn is accepted without claiming that the snapshot proves intra-turn order;
the supervisor remains authoritative for proposal validation and binding.

The follow-up B1 run exposed a separate skill-side omission: the typed proposal
contained three output contracts, while the generated `spec.py` wired no
`custom(...)` verifiers. This change makes the one-for-one contract inventory
and API input-phase limitation explicit at the workflow-v2/generator handoff;
it keeps the supervisor's `closure.contract_inventory_mismatch` rejection
strict. There is still no valid paired public arm that isolates this instruction
change from the rest of the live workflow, so this entry remains `NO_EVAL`.

The rebuilt v2 run also exposed a source-span authoring trap: a `###` decision
span was widened to include its heading and blank lines, so the supervisor
correctly rejected `v3.provenance.span_mismatch`. The workflow reference now
requires copying all four coordinates from the trusted parser and makes clear
that a subsection's `.text` span covers only its body. This remains a contract
clarification rather than a measured scenario improvement; the attempted live
run ended at the provider session limit before capture. The supervisor-side
diagnostic now also returns the expected four coordinates in structured error
data for this specific mismatch, without returning source text or weakening
the validation boundary.

## Evidence

- `evals/dp-scenarios/tests/test_grading_gates.py` — exact path/content binding,
  same-turn snapshot handling, and missing-file rejection.
- `evals/dp-scenarios/tests/test_runner_tier.py` — populated workflow-v2
  replays carrying a validator-backed v3 proposal-file evidence shape; the
  caller omits `source_hash` and the focused test validates the supervisor-
  materialized form.
- `evals/tests/test_workflow_v2_job_loop_contract.py` — the shipped skill's
  prepare-before-consent, inline typed-proposal, and exact executable contract
  inventory instructions, including exact parser source-span guidance.
