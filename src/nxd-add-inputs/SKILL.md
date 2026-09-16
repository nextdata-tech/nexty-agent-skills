---
name: nxd-add-inputs
description: Add or repair inputs in a Nextdata OS Python data product. Use when adding source-aligned inputs, upstream data-product inputs, API inputs, input semantic models, transform parameters, or input expectations in files such as spec.py, models.py, transform.py, contracts, or local validation scripts.
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
  version: 0.51.0
---

# NXD Adding Inputs

Add inputs to an existing Nextdata OS Python data product without disturbing unrelated outputs, policies, or transform logic.

## Setup

- Confirm `nxd-setup-cli` has selected the mesh and produced `<session_config>`.
- Resolve `<app_url>` from the active mesh registry and use docs paths:
  - `<app_url>/docs/#/tutorials/guides/04-inputs`
  - `<app_url>/docs/#/tutorials/guides/01-semantic-model`
  - `<app_url>/docs/#/tutorials/guides/05-expectations`
  - `<app_url>/docs/#/tutorials/guides/consumer-tutorial`
- On Windows PowerShell, translate `<session_config>` and temp paths using `nxd-setup-cli` conventions.
- If no local infra-profile YAML is available, list profiles with
  `nxd ls infra-profiles --config=<session_config>` and list a chosen profile's
  services with `nxd --config=<session_config> rest -u /api/v1/infraprofiles/<profile-name>/services`.

## Workflow

1. Inspect `spec.py`, `models.py`, `transform.py`, `requirements.txt` or `pyproject.toml`, `.nxdignore`, and existing `contracts/`.
2. Classify the new input:
   - External storage or API source: use a source-aligned input and a service URL from the active infra profile.
   - Upstream data product: use a data-product input and confirm the upstream output port and model from the mesh or DP REST API.
   - Off-mesh API: model the request/response shape, keep credentials out of source, and add a local fetch/parse smoke test.
3. Confirm the input name, service name, driver/context type, source location, model schema, and refresh behavior with the user. Do not invent infra profile names, domains, service names, or identity values.
4. Add or update the semantic model. Prefer one semantic model per unique schema; avoid complex types when a string representation is safer for the platform.
5. Add the input declaration in `spec.py`. Use the real active mesh app host in service URLs; examples from public repos are templates, not values to copy.
6. Update `transform.py`. The transform parameter name must match the input name after Python normalization: hyphens become underscores.
7. If the input needs a contract, add an input expectation, not an output promise. Schema or custom expectations belong on the input side; use `nxd-add-expectations-and-promises` for the custom verify template and `VerifyResultEnum` values.
8. Update local validation so it exercises fetch, parse, and shape logic. Do not stop at "the source is reachable."
9. Run validation:

```bash
nxd --config <session_config> whoami
nxd validate --config <session_config> <data_product_directory> --debug
echo "nxd validate exit code: $?"
```

`nxd validate` resolves infra-profile services against the `--config` mesh. If
`whoami` prints `Not logged in`, record validation as `NOT RUN` even if the
shell exit code is `0`.

## Guardrails

- Do not create one input per file when one service-level input is the correct product boundary.
- Do not leak passwords, tokens, access keys, presigned URLs, or PEM content into chat or generated source.
- Do not copy demo hosts, demo infra profiles, or placeholder emails from examples.
- If input docs conflict with a reference example, the user's input docs win.
