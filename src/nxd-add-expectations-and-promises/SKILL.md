---
name: nxd-add-expectations-and-promises
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
  version: 0.38.3
---

# NXD Expectations and Promises

Use expectations to protect inputs before transform execution, and promises to verify outputs after writes.

## Setup

- Confirm `nxd-setup-cli` has selected the mesh and produced `<session_config>`.
- Resolve `<app_url>` from the active mesh registry and use docs paths:
  - `<app_url>/docs/#/tutorials/guides/05-expectations`
  - `<app_url>/docs/#/tutorials/guides/03-promises`
  - `<app_url>/docs/#/tutorials/cli/data_quality`
  - `<app_url>/docs/#/basics/transactional_guarantees`

## Decision Rule

- Input quality or access check before transform: add an expectation to the input.
- Output quality guarantee after transform writes: add a promise to the output port.
- Computational policy requiring data quality: add the contract here, then use `nxd-add-policies` or `nxd-toggle-policies` to activate enforcement.

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
nxd --config <session_config> whoami
nxd validate --config <session_config> <data_product_directory> --debug
```

`nxd validate` imports and validates the spec, but it does not execute custom
verify functions against live data. Verify functions run as platform contracts
at the relevant expectation/promise phase.

## Custom Input Expectation Template

Use this when an input must be checked by calling the upstream source or
inspecting its driver context. The parameter name must match the `.input(...)`
name after Python normalization: `"jira-api"` becomes `jira_api`.

```python
# spec.py
from contracts import jira_input_format

.input(
    "jira-api",
    source_aligned_input()
    .source(JIRA_API_URL)
    .model(jira_issue)
    .expectation(
        custom("jira_input_format").verify(code(jira_input_format.verify))
    ),
)
```

```python
# contracts/jira_input_format.py
from nxd.data_product.context import API, Model, VerifyResult, VerifyResultEnum


def verify(jira_api: API, models: dict[str, Model]) -> VerifyResult:
    failures: list[str] = []
    # Use jira_api.url / jira_api.username / jira_api.token, but never echo
    # secrets into logs, exceptions, or the returned context.

    if failures:
        return VerifyResult(
            VerifyResultEnum.FAILED,
            {"failures": failures},
        )

    return VerifyResult(
        VerifyResultEnum.PASS,
        {"checked": True},
    )
```

Known `VerifyResultEnum` values include `PASS`, `WARNING`, and `FAILED`; use
`FAILED`, not `FAIL`. Return `WARNING` only for soft conditions that should be
visible but not blocking under the active policy consequence.

## Custom Output Promise Template

Promises attach to an output **port**, not to the `.output(...)` wrapper or the
model declaration:

```python
.output(
    data_product_output()
    .port(
        "pgvector",
        storage(PGVECTOR_URL).config(pg_vector_config()),
    )
    .promise(custom("row_count").verify(code(row_count.verify)).model(jira_embeddings))
    .model(jira_embeddings)
)
```

## Guardrails

- Do not attach output promises to input declarations.
- Do not attach input expectations to output ports.
- Do not disable a policy because a contract is missing; add the required contract or explain the missing artifact.
- Do not expose sample rows with sensitive values in the final answer.
- Do not put secrets, tokens, or raw sensitive sample rows in `VerifyResult.context`; return counts, issue keys, field names, or redacted snippets only.
