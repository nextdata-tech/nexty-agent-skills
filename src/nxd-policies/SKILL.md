---
name: nxd-policies
description: List, activate, and deactivate Nextdata computational policies on a data product via the public nxd CLI. Use whenever the user asks to list policies for a data product, or to toggle / deactivate / activate / reactivate a policy on a mesh. Covers CLI flag quirks that differ from older documentation, plus the canonical verify-toggle-verify sequence.
allowed-tools:
  - Bash
  - Read
metadata:
  author: nextdata
  version: 0.1.0
---

# nxd Policies

Manage computational policies on Nextdata data products. Three operations: **list**, **deactivate**, **activate**. The CLI flag surface is subtle — follow the patterns below rather than guessing.

## Prerequisites

- `nxd` CLI installed and a mesh selected (see `nxd-setup` skill if not).
- You know the data product name (e.g. `sales-influence-insights`) and target environment (e.g. `demo`).
- For **activation**, you know the policy's full configuration: policy type, validation contract name, filter, consequence. These usually live in the repo under `<dp>/policies/create.sh` — read that file first instead of inventing values.

---

## List policies for a data product

```bash
nxd ls policies --dp <dp-name> --env <env>
```

- Use `--dp <name>`, **not** `data-product policies --name <name>` (older docs are wrong).
- Add `--show-inactive` to include deactivated policies.
- Output shows each activation's `ID`, `Policy` type, `Name`, `Consequence`, and `DP Activation ID`.

Example:

```bash
nxd ls policies --dp sales-influence-insights --env demo
```

---

## Deactivate a policy

```bash
nxd deactivate policy --skip-version-check --name <policy-name>
```

- **Do not pass `--env`** — `nxd deactivate policy` does not accept it. Deactivation is global by policy name.
- The contract behind the policy is **not** deleted, so you can reactivate later without recreating it.
- Use `--id <activation-id>` instead of `--name` if you have the numeric ID from the list step.

Example:

```bash
nxd deactivate policy --skip-version-check --name data_completeness_90_percent
```

For a **full teardown** (delete the policy and contract, not just deactivate):

```bash
nxd deactivate policy --skip-version-check --name <policy-name>
nxd delete policy     --skip-version-check --name <policy-name>
nxd delete contract   --skip-version-check --yes <contract-name>
```

---

## Activate a policy

`activate policy` re-uses an existing contract. The required flags depend on policy type.

### DataQualityCompliance (contract-driven)

```bash
nxd activate policy --skip-version-check \
  --name <policy-name> \
  --policy DataQualityCompliance \
  --validation-url <contract-name> \
  --output-ports at-least-one \
  --filter '.name == "<dp-name>"' \
  --consequence STOP \
  --promise-enforced \
  --env <env>
```

### SensitivityCompliance (parameters-driven)

```bash
nxd activate policy --skip-version-check \
  --name <policy-name> \
  --policy user:SensitivityCompliancePolicy \
  --parameters-file ./sensitivity-policy.json \
  --filter '.name == "<dp-name>"' \
  --consequence STOP \
  --env <env>
```

Notes:

- `--env` **is** required for activation (unlike deactivate).
- `--parameters-file` is a relative path — `cd` into the data product directory before running, or use an absolute path.
- If the contract does not yet exist, create it first: `nxd create contract --skip-version-check --name <contract-name> --code ./contracts/<file>.py --description "..."`.

---

## Canonical verify-toggle-verify sequence

Use this when the user wants to demo turning a policy off and on. Substitute `<dp>`, `<policy>`, `<contract>`, `<env>`.

```bash
# 1. list (baseline)
nxd ls policies --dp <dp> --env <env>

# 2. deactivate
nxd deactivate policy --skip-version-check --name <policy>

# 3. list (verify it dropped)
nxd ls policies --dp <dp> --env <env>

# 4. activate (cd into the DP dir if --parameters-file paths are relative)
nxd activate policy --skip-version-check \
  --name <policy> \
  --policy DataQualityCompliance \
  --validation-url <contract> \
  --output-ports at-least-one \
  --filter '.name == "<dp>"' \
  --consequence STOP \
  --promise-enforced \
  --env <env>

# 5. list (verify it returned)
nxd ls policies --dp <dp> --env <env>
```

Always **run step 1 first** before handing the chain to the user. It confirms env reachability, the exact policy name, and surfaces any further CLI drift.

---

## Common gotchas

- **Redeploy re-applies policies.** A deploy pipeline that re-applies a data product's declared policies will **overwrite manual deactivations** on the next deploy. Warn the user when toggling a policy for a demo — re-check with `ls policies` after any redeploy.
- **`--env` only on `ls` and `activate`.** Not on `deactivate`, not on `delete policy`, not on `delete contract`.
- **`--skip-version-check`** is conventional on every mutating command in Nextdata repos; include it to match repo scripts.
- **Filter syntax is `jq`-style:** `.name == "<dp>"` for a single DP, `.domain == "retail/sales"` for a domain-wide policy.
- **Policy name vs contract name** are usually the same string in convention but conceptually distinct — `--validation-url` always references the contract.

