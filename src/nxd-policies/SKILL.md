---
name: nxd-policies
description: List, activate, deactivate, and build/deploy Nextdata computational policies. Use whenever the user asks to list policies for a data product, toggle / deactivate / activate / reactivate a policy, build a new WASM policy, or deploy a policy to a mesh. Covers CLI flag quirks that differ from older documentation and links to the reference policy implementations in nextdata-tech/nxd-policies.
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

- **CI re-applies on deploy.** Repos often run `policies/delete-all.sh && policies/create-all.sh` after every deploy (see `.github/workflows/deploy-data-products.yml`). Manual deactivations get **wiped on the next deploy**. Warn the user when toggling for a demo.
- **`--env` only on `ls` and `activate`.** Not on `deactivate`, not on `delete policy`, not on `delete contract`.
- **`--skip-version-check`** is conventional on every mutating command in Nextdata repos; include it to match repo scripts.
- **Filter syntax is `jq`-style:** `.name == "<dp>"` for a single DP, `.domain == "retail/sales"` for a domain-wide policy.
- **Policy name vs contract name** are usually the same string in convention but conceptually distinct — `--validation-url` always references the contract.

---

## Where to find a DP's policy/contract definitions

Source of truth in a repo:

- `policies/create-all.sh` — global policies + per-DP includes.
- `policies/delete-all.sh` — mirror.
- `data-products/.../<dp>/policies/{create,delete}.sh` — per-DP commands; copy flag values from here when constructing an `activate` command.
- `data-products/.../<dp>/contracts/*.py` — the contract code referenced by `--validation-url`.

Read these before composing an activate command. Do not invent flag values.

---

## Build and deploy a new policy (WASM)

Reference implementations of Nextdata governance policies live in **[nextdata-tech/nxd-policies](https://github.com/nextdata-tech/nxd-policies)**. Policies are Rust crates compiled to WASM modules that the NXD policy engine evaluates against assembled data product context.

The repo's README is the source of truth — fetch it first if you're guiding a user through authoring a new policy:

```bash
gh api repos/nextdata-tech/nxd-policies/contents/README.md --jq '.content' | base64 -d
```

### Prerequisite

```bash
rustup target add wasm32-unknown-unknown
```

SDK reference: [nextdata-tech/nxd-policy-sdk](https://github.com/nextdata-tech/nxd-policy-sdk) — provides the `#[nxd_policy]` attribute, subscription types, and the `evaluate` contract.

### Author a new policy

1. **Clone** `nxd-policies` and **copy** the directory whose existing policy is closest to what you need (see policy table below).
2. **Rename** the directory and update `Cargo.toml`: change `name`, `version`, adjust subscriptions declared in `#[nxd_policy]`.
3. **Implement** `evaluate` in `src/lib.rs` — return `satisfied: bool` plus any violations.
4. **Build** and **deploy** with the commands below.

Reference policies in the repo (use as templates):

| Directory | Crate name | Enforces |
|-----------|-----------|----------|
| `attribute-encryption/` | `attribute_encryption` | sensitive attributes encrypted at metadata + infra level |
| `guarantee-model-output/` | `guarantee_model_output` | every output model has a promise |
| `mandatory-glossary-policy/` | `mandatory_glossary_policy` | fields linked to a GlossaryTerm |
| `mandatory-metadata-compliance/` | `mandatory_metadata_compliance` | required metadata fields present + non-empty |
| `mandatory-owner-policy/` | `mandatory_owner_policy` | DP spec declares an owner with a principal |
| `minimum-quality-level-policy/` | `minimum_quality_level_policy` | min count of promises + expectations |
| `naming-convention-compliance/` | `naming_convention_compliance` | DP kebab-case, models/fields snake_case |
| `semantic-compliance/` | `semantic_compliance` | required attributes present in all output models |
| `semantic-tag-compliance/` | `semantic_tag_compliance` | model fields matching patterns carry required semantic tags |
| `sensitivity-compliance/` | `sensitivity_compliance` | specified sensitive attributes absent from output models |
| `storage-isolation-policy/` | `storage_isolation_policy` | S3 bucket names match `{domain}-*`, optional region allowlist |

### Build

```bash
# All policies
make build-all

# Single policy
make build-<crate_name>           # e.g. make build-mandatory_owner_policy

# Or directly with cargo
cargo build -p <crate_name> --target wasm32-unknown-unknown --release
```

Output: `target/wasm32-unknown-unknown/release/<crate_name>.wasm`.

### Deploy the WASM (policy definition)

`nxd policies deploy` registers the policy *definition* (extracted from the WASM binary's `name` and `version`):

```bash
nxd policies deploy --wasm target/wasm32-unknown-unknown/release/<crate_name>.wasm
```

This makes the policy available to activate. It does not yet apply to any data products.

### Activate the deployed policy on data products

`nxd policies activate` matches data products by a `jq`-style filter and applies the policy with a consequence:

```bash
nxd policies activate \
  --policy <PolicyName> \
  --filter '.domain == "finance"' \
  --env production \
  --consequence STOP \
  --name <activation-name>
```

- `<PolicyName>` is the declared name inside the WASM (e.g. `MandatoryOwnerPolicy`), not the crate name.
- `<activation-name>` is the user-visible label that will appear in `nxd ls policies`.
- Same `--filter` semantics as the activation section above (`.name == "<dp>"` for single DP, `.domain == "..."` for domain scope).

### End-to-end: list deployed policy definitions

```bash
nxd ls policies --definitions
```

Use this to confirm a newly-deployed WASM is registered before activating it on data products.

### Example data products

Some policies in `nxd-policies` ship with `examples/compliant-dp/` and `examples/violating-dp/` subdirectories — useful for end-to-end testing. Deploy with:

```bash
export NXD_CLUSTER=app.nxd.local
nxd launch --dir policies/<policy-dir>/examples/compliant-dp
```
