---
name: nxd-adding-policy
description: Add or activate a Nextdata OS computational policy for a data product or domain. Use when creating or registering a contract, adding policy parameters, activating DataQualityCompliance, SensitivityCompliance, SemanticCompliance, AttributeEncryption, or NoOp policies, or producing safe nxd CLI policy commands.
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
  version: 0.25.4
---

# NXD Adding Policy

Add computational policy enforcement without guessing CLI flags, env names, domains, or data-product filters.

## Setup

- Confirm `nxd-setup` has selected the mesh and produced `<session_config>`.
- Use `nxd-policies` for low-level list/deactivate/activate command details.
- Resolve `<app_url>` from the active mesh registry and use docs paths:
  - `<app_url>/docs/#/tutorials/guides/policy-tutorial`
  - `<app_url>/docs/#/dp_development/policies`
  - `<app_url>/docs/#/tutorials/cli/data_quality`
  - `<app_url>/docs/#/tutorials/guides/03-promises`
  - `<app_url>/docs/#/tutorials/guides/05-expectations`

## Workflow

1. Identify the policy type and target: one data product, multiple data products, or a domain.
2. Derive or elicit `--env`, target data product names, domain names, policy name, consequence, and output/input enforcement scope. Do not default these values.
3. Run `nxd activate policy --help` if there is any doubt about current flags.
4. For DataQualityCompliance, ensure the data product has the required promise and/or expectation before activation.
5. For parameters-driven policies, create or inspect the parameters JSON file. Keep it in the data-product repo when that matches local convention.
6. If a computational contract is needed, register it first:

> **`--skip-version-check`** bypasses the CLI-vs-mesh version compatibility check. It is shown here only to keep these examples runnable across mesh versions during authoring. Drop it for normal use; add it back **only** when the CLI blocks on a version mismatch you have confirmed is safe to ignore.

```bash
nxd --config <session_config> create contract --skip-version-check \
  --name <contract-name> --code ./contracts/<file-or-dir> --description "<description>"
```

7. Activate with the current CLI shape. Example for a data-quality promise policy:

```bash
nxd --config <session_config> activate policy --skip-version-check \
  --name <policy-name> \
  --policy DataQualityCompliance \
  --validation-url <contract-name> \
  --output-ports at-least-one \
  --filter '.name == "<dp-name>"' \
  --consequence STOP \
  --promise-enforced \
  --env <env>
```

8. Example for a parameters-driven sensitivity policy:

```bash
nxd --config <session_config> activate policy --skip-version-check \
  --name <policy-name> \
  --policy SensitivityCompliance \
  --namespace user \
  --parameters-file ./sensitivity-policy.json \
  --filter '.name == "<dp-name>"' \
  --consequence STOP \
  --env <env>
```

9. Verify:

```bash
nxd --config <session_config> ls policies --dp <dp-name> --env <env>
```

## Guardrails

- Do not disable policy enforcement to make a product pass.
- Do not use obsolete namespace-qualified policy class names unless `nxd activate policy --help` in the user's environment explicitly requires them.
- Do not run mutating commands until the user has confirmed env, target, consequence, and filter.
