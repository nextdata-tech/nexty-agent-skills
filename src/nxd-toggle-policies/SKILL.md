---
name: nxd-toggle-policies
description: List, activate, and deactivate Nextdata computational policies on a data product via the public nxd CLI. Use when the user asks to list policies for a data product, or to toggle, deactivate, activate, or reactivate a policy on a mesh. Covers CLI flag quirks that differ from older documentation, plus the canonical verify-toggle-verify sequence.
allowed-tools:
  - Bash
  - Read
metadata:
  author: nextdata
  version: 0.35.0
---

# nxd Policies

Manage computational policies on Nextdata data products. Three operations: **list**, **deactivate**, **activate**. The CLI flag surface is subtle — follow the patterns below rather than guessing.

## Prerequisites

- `nxd` CLI installed and a mesh **selected and configured** (the `nxd-setup-cli` skill owns this; run it first if no mesh is active).
- **Target the selected mesh on every command.** `nxd-setup-cli` writes a per-session config to `<session_config>`; pass `--config <session_config>` to **every** `nxd` invocation below so policies are toggled on the intended platform. The mesh host (app/api URL) comes from the registry via that config — never hardcode a host. On Windows PowerShell, `<session_config>` is usually `$env:TEMP\nxd-<mesh_name>.yaml`; on POSIX/WSL it is usually `/tmp/nxd-<mesh_name>.yaml`.

**Elicit or derive these up front** (do not assume values — confirm before running any mutating command):

- **Environment (`--env`)** — required by `ls` and `activate`. A single mesh may host multiple envs, so the env is not implied by the mesh. Ask the user which env, or derive it from the selected mesh; do not default to a specific name.
- **Data product name** — ask the user, or derive via `nxd --config <session_config> ls data-products`.
- **Domain** (only for domain-wide filters) — ask the user, or derive via `nxd --config <session_config> ls domains`.
- **Infra-profile** (if creating/activating a contract on the mesh requires one) — ask the user, or derive via `nxd --config <session_config> ls infra-profiles`.
- For **activation**, you also need the policy's full configuration: policy type, validation contract name, filter, consequence, output ports. These usually live in the repo under `<dp>/policies/create.sh` — read that file first instead of inventing values. **If that file is absent, elicit each value from the user** rather than guessing.

> **Platform docs.** Docs are served per-mesh at `<app_url>/docs/#/<path>`, where `<app_url>` is the active mesh's app host from the nxd registry (resolve it, do not hardcode; the `#/` hash route is required, omit any `.md`). Hand these out inline when the user is stuck on a concept. Most relevant here: `tutorials/guides/policy-tutorial`, `tutorials/cli/data_quality`, `tutorials/guides/03-promises`, `tutorials/guides/05-expectations`, and `tutorials/cli/setup`. If a deep link 404s, open `<app_url>/docs/#/` and navigate the sidebar.

---

## List policies for a data product

```bash
nxd --config <session_config> ls policies --dp <dp-name> --env <env>
```

- Use `--dp <name>`, **not** `data-product policies --name <name>` (older docs are wrong).
- Add `--show-inactive` to include deactivated policies.
- Output shows each activation's `ID`, `Policy` type, `Name`, `Consequence`, and `DP Activation ID`.

Example (placeholders `<mesh_name>`, `<dp-name>`, `<env>` — substitute the active mesh, the DP from `nxd ls data-products`, and the elicited env; the names below are illustrative, not canonical):

```bash
nxd --config <session_config> ls policies --dp <dp-name> --env <env>
```

---

## Deactivate a policy

```bash
nxd --config <session_config> deactivate policy --skip-version-check --name <policy-name>
```

- **Do not pass `--env`** — `nxd deactivate policy` does not accept it. Deactivation is global by policy name.
- The contract behind the policy is **not** deleted, so you can reactivate later without recreating it.
- Use `--id <activation-id>` instead of `--name` if you have the numeric ID from the list step.

Example (substitute `<mesh_name>` and the real policy name from the list step):

```bash
nxd --config <session_config> deactivate policy --skip-version-check --name <policy-name>
```

For a **full teardown** (delete the policy and contract, not just deactivate):

```bash
nxd --config <session_config> deactivate policy --skip-version-check --name <policy-name>
nxd --config <session_config> delete policy     --skip-version-check --name <policy-name>
nxd --config <session_config> delete contract   --skip-version-check --yes <contract-name>
```

---

## Activate a policy

`activate policy` re-uses an existing contract. The required flags depend on policy type.

### DataQualityCompliance (contract-driven)

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

- `--promise-enforced` ties the policy to the DP's promise. Docs: `<app_url>/docs/#/tutorials/guides/03-promises` (promise semantics) and `<app_url>/docs/#/tutorials/cli/data_quality` (data-quality contracts). Resolve `<app_url>` from the active mesh config.
- `--output-ports at-least-one` controls which output ports the policy targets. Docs: `<app_url>/docs/#/tutorials/guides/02-outputs`.

### SensitivityCompliance (parameters-driven)

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

Notes:

- `--env` **is** required for activation (unlike deactivate). Elicit/derive it as described in Prerequisites — do not assume a default env.
- `--policy` takes the policy type name shown by `nxd activate policy --help` (for example `SensitivityCompliance`), while `--namespace` carries `user` or `nextdata`.
- `--parameters-file` is a relative path — `cd` into the data product directory before running, or use an absolute path.
- If the contract does not yet exist, create it first against the **same mesh config**:
  ```bash
  nxd --config <session_config> create contract --skip-version-check \
    --name <contract-name> --code ./contracts/<file>.py --description "..."
  ```
  Contract/policy creation reference: `<app_url>/docs/#/tutorials/cli/create`. What a computational policy enforces: `<app_url>/docs/#/tutorials/guides/05-expectations`.

---

## Canonical verify-toggle-verify sequence

Use this when the user wants to demo turning a policy off and on. Substitute `<mesh_name>` (active mesh), `<dp>`, `<policy>`, `<contract>`, `<env>` — all elicited/derived per Prerequisites, none assumed.

```bash
# 1. list (baseline)
nxd --config <session_config> ls policies --dp <dp> --env <env>

# 2. deactivate
nxd --config <session_config> deactivate policy --skip-version-check --name <policy>

# 3. list (verify it dropped)
nxd --config <session_config> ls policies --dp <dp> --env <env>

# 4. activate (cd into the DP dir if --parameters-file paths are relative)
nxd --config <session_config> activate policy --skip-version-check \
  --name <policy> \
  --policy DataQualityCompliance \
  --validation-url <contract> \
  --output-ports at-least-one \
  --filter '.name == "<dp>"' \
  --consequence STOP \
  --promise-enforced \
  --env <env>

# 5. list (verify it returned)
nxd --config <session_config> ls policies --dp <dp> --env <env>
```

Always **run step 1 first** before handing the chain to the user. It confirms env reachability, the exact policy name, and surfaces any further CLI drift.

Toggling a policy directly changes what consumers of the DP see — for how policy state affects downstream consumers, see `<app_url>/docs/#/tutorials/guides/consumer-tutorial` (resolve `<app_url>` from the active mesh config).

---

## Common gotchas

- **Redeploy re-applies policies.** A deploy pipeline that re-applies a data product's declared policies will **overwrite manual deactivations** on the next deploy. Warn the user when toggling a policy for a demo — re-check with `ls policies` after any redeploy. How that state change reaches consumers: `<app_url>/docs/#/tutorials/guides/consumer-tutorial`.
- **`--env` only on `ls` and `activate`.** Not on `deactivate`, not on `delete policy`, not on `delete contract`.
- **`--skip-version-check`** is conventional on every mutating command in Nextdata repos; include it to match repo scripts.
- **Filter syntax is `jq`-style:** `.name == "<dp>"` for a single DP, or `.domain == "<domain>"` for a domain-wide policy. The `<domain>` value is mesh/env-specific taxonomy — **elicit it from the user or derive it** via `nxd --config <session_config> ls domains`; do not hardcode a domain string. For the DP/domain fields these selectors match against, see `<app_url>/docs/#/tutorials/guides/01-semantic-model`.
- **Policy name vs contract name** are usually the same string in convention but conceptually distinct — `--validation-url` always references the contract.
