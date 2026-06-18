# Scenario Template: Artifact-Required Data Product Build

Copy this template into `evals/private/<customer-or-demo>/<scenario-name>/prompt.md` when measuring a customer-specific or commercial-demo workflow.

Do not commit the copied private scenario if it contains customer names, schemas, transcripts, logs, proprietary requirements, or internal commercial-demo material.

## Scenario

Build or reproduce the data-product workflow from the supplied artifacts, then measure how many steps and errors were required with each skill set.

## Required Artifacts

- Source requirements
- Input schema examples
- Output schema examples
- Existing human/agent workflow notes, transcript, or git commits
- Expected final data-product files or acceptance diff, if available
- Expected policy, promise, and expectation requirements
- Sandbox mesh details, or explicit instruction to stop before `nxd launch`

## Task For The Agent

Recreate the data product from the supplied artifacts. Preserve the artifact's business requirements, data contracts, input/output semantics, policy requirements, scheduling, and validation expectations.

## Success Checks

- Generated inputs match the supplied source requirements and schemas.
- Generated outputs and output ports match the supplied target requirements and schemas.
- Expectations and promises are attached on the correct side of the product boundary.
- Policies are satisfied rather than disabled.
- Transform signatures match declared input and output-port names.
- Local validation or smoke tests cover fetch, parse, transform, and output-shape logic.
- `nxd validate` is run when a sandbox/config is available; failures are debugged rather than ignored.
- Final handover lists exact commands run, unresolved artifacts, and remaining manual work.

## Metrics

Record the metrics from `evals/README.md`: elapsed time, assistant turns, tool calls, error count, course corrections, token usage, success, and variance notes.
