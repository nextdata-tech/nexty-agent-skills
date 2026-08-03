---
name: nxd-fix-policy-failures
description: Diagnose and fix a Nextdata OS data product that is failing a computational policy. Use when policy violations, failed promises, failed expectations, blocked consumers, STOP or WARN policy consequences require updates to spec.py, contracts, models, transform.py, policy parameters, or validation commands.
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
  version: 0.32.1
---

# NXD Policy Compliance Fix

Fix the data product or contract that violates a policy. Do not make the policy disappear unless the user explicitly asks for a temporary demo toggle.

## Setup

- Confirm `nxd-setup-cli` has selected the mesh and produced `<session_config>`.
- Use `nxd-toggle-policies` for exact policy list/activate/deactivate syntax.
- Resolve `<app_url>` from the active mesh registry and use docs paths:
  - `<app_url>/docs/#/tutorials/guides/policy-tutorial`
  - `<app_url>/docs/#/tutorials/guides/03-promises`
  - `<app_url>/docs/#/tutorials/guides/05-expectations`
  - `<app_url>/docs/#/dp_development/debugging`

## Workflow

1. Capture the failure state before editing:

```bash
nxd --config <session_config> ls policies --dp <dp-name> --env <env> --show-inactive
nxd --config <session_config> describe data-product <dp-name> --compute-status
nxd --config <session_config> logs <dp-name> --debug-logs
```

2. Identify policy type, policy name, consequence, target filter, activation ID, validation contract, output/input scope, and the DP activation ID when present.
3. Map the failure:
   - Missing input check: add or repair an expectation.
   - Missing output guarantee: add or repair a port-level promise.
   - Contract code error: fix `contracts/` and re-register or redeploy as required by the repo flow.
   - Policy parameter mismatch: fix the parameters file and reactivate with the current CLI syntax.
   - Runtime failure before contract execution: use `nxd-debug-data-product` first.
4. Inspect `spec.py`, `models.py`, `transform.py`, `contracts/`, and any `policies/` scripts. Prefer existing repo conventions over new structure.
5. Patch the smallest surface that makes the product comply.
6. Validate locally and structurally:

```bash
nxd validate --config <session_config> <data_product_directory> --debug
```

7. If deployed state must be refreshed, tell the user the exact launch or retry command. Use `nxd run --retry`, not a nonexistent retry subcommand.
8. Re-check the policy list and data-product compute status.

## Guardrails

- Do not deactivate, delete, or weaken a policy as the compliance fix.
- Do not guess `--env`; derive or ask.
- Do not confuse promise placement with expectation placement.
- Do not hide failed verification. Report the exact command and result.
