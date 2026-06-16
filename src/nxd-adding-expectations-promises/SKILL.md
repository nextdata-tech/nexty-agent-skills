---
name: nxd-adding-expectations-promises
description: Add, repair, or explain Nextdata OS input expectations and output promises. Use when adding data-quality contracts, schema checks, custom verify functions, promise files, expectation files, or fixing confusion between input-side expectations and output-port promises.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - MultiEdit
  - Glob
  - Grep
  - AskUserQuestion
metadata:
  author: nextdata
  version: 0.1.0
---

# NXD Expectations and Promises

Use expectations to protect inputs before transform execution, and promises to verify outputs after writes.

## Setup

- Confirm `nxd-setup` has selected the mesh and produced `<session_config>`.
- Resolve `<app_url>` from the active mesh registry and use docs paths:
  - `<app_url>/docs/#/tutorials/guides/05-expectations`
  - `<app_url>/docs/#/tutorials/guides/03-promises`
  - `<app_url>/docs/#/tutorials/cli/data_quality`
  - `<app_url>/docs/#/basics/transactional_guarantees`

## Decision Rule

- Input quality or access check before transform: add an expectation to the input.
- Output quality guarantee after transform writes: add a promise to the output port.
- Computational policy requiring data quality: add the contract here, then use `nxd-adding-policy` or `nxd-policies` to activate enforcement.

## Workflow

1. Inspect `spec.py`, `models.py`, `contracts/`, and transform output paths.
2. Identify whether the requested check is input-side, output-side, or both.
3. Choose contract style:
   - Schema/model check when the model alone expresses the requirement.
   - Custom Python verify function when the check needs API calls, row counts, PII detection, cross-field logic, or output data inspection.
   - Soda or Great Expectations only when the data product already uses that tool or the user asks for it.
4. Add or update the contract file under `contracts/`.
5. Wire it in `spec.py`:
   - expectation on the input declaration.
   - promise on the output port declaration.
6. Keep contract code deterministic and side-effect-light. It should verify data, not mutate business tables.
7. Update local validation or a focused contract smoke test when possible.
8. Run:

```bash
nxd validate --config <session_config> <data_product_directory> --debug
```

## Guardrails

- Do not attach output promises to input declarations.
- Do not attach input expectations to output ports.
- Do not disable a policy because a contract is missing; add the required contract or explain the missing artifact.
- Do not expose sample rows with sensitive values in the final answer.
