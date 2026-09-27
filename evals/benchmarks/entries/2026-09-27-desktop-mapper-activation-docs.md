---
id: 2026-09-27-desktop-mapper-activation-docs
date: 2026-09-27
label: "document the shipped five-requirement mapper activation (nxd #7997)"
plugin_version: 0.54.1
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — document the shipped five-requirement mapper activation (nxd #7997)

## Notes

nxd #7997 (WP12 of the Desktop workflow-v2 mapper admission design) ships the
activation that the 2026-09-26 mapper approval docs described as missing. The
bundled contract now has five requirements: consent, capture, review,
`approval` (`mapper-confirmation-v1`), validation. A non-mapper closure
completes the approval as `not_present` with no prompt. The formal-approval
policy allows provider `anthropic`, the priced haiku, sonnet, opus and fable
model ids (exact match), 1000 calls, 2,000,000 tokens and 25 USD per approval,
100 USD lifetime, no recurring grants, and 300/120/30 s windows. Setup keeps the
previously activated contract when workflow instances exist.

`field-mapper.md` § Desktop supervisor approval boundary and `workflow-v2.md`
§ Mapper approval now describe that bundle and its policy. Because the pack is
also used against older supervisors, and against upgraded installs that kept a
four-requirement contract, they tell the agent to read the contract from the
requirements `prepare_workflow` returns. On a four-requirement contract a
mapper closure still stops at `validation/mapper_closure_unsupported`.

This is a documentation correction. No public `evals/run.py` scenario can
exercise it: the approval needs the supervisor's native OS dialog, and the
headless nxd eval (WP13) does not exist.

## Evidence

- `evals/tests/test_mapper_supervisor_approval_contract.py` —
  `test_desktop_mapper_flow_is_the_shipped_workflow_v2_requirement` and
  `test_workflow_docs_match_the_shipped_supervisor_codes` fail against the
  previous docs. They require the five-requirement contract, the no-prompt
  `not_present` completion, the policy ceilings, the setup behaviour for
  existing instances and the older-supervisor path, and they reject the stale
  "activation bundled with Desktop today" wording.
