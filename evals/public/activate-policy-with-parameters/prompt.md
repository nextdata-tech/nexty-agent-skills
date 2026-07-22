# Scenario: Activate a Parameters-Driven Sensitivity Policy

The eval runner provides the `customer-profiles-curated` data-product directory,
saved `nxd` CLI output from the active mesh session, and the CLI help text for
the commands involved. The mesh session config is `/tmp/nxd-acme-prod.yaml` and
the user is already authenticated.

Task for the agent:

Our compliance team wants the `customer-profiles-curated` data product to enforce
a sensitivity policy on the `prod` environment of the acme-prod mesh. Someone on
the team already wrote the contract code at `contracts/sensitivity_rules.py`, but
as far as I know nothing has been switched on for it yet.

The policy should be called `enforce-profile-sensitivity`, it should apply to the
`customer-profiles-curated` data product, and a violation must block — I do not
want a warning that people ignore. The contract should be registered under the
name `profile-sensitivity`.

Read the fixtures in the workspace to work out the current state, then write out
everything I need: any files that have to exist before the commands run, and the
exact `nxd` commands in the order I should run them, including how I confirm
afterwards that it is actually on. Save the commands to `activate-policy.sh`. If
the commands need to read a parameters file, name it `policy-parameters.json` and
put it next to the data product where the runbook lives.

There is an old runbook checked in under `policies/` — treat it as unverified;
the CLI help in the fixtures is what the installed CLI actually accepts.

Required artifacts from eval runner:

- `fixtures/data_product/` — spec.py, models.py, contracts/sensitivity_rules.py, policies/README-runbook.md
- `fixtures/nxd-activate-policy-help.txt`, `fixtures/nxd-create-contract-help.txt`
- `fixtures/nxd-ls-contracts.txt`, `fixtures/nxd-ls-policies.txt`, `fixtures/nxd-ls-data-products.txt`

Success checks:

- The agent registers the contract before activating the policy that references it.
- The agent derives the policy parameters from the contract code rather than inventing them.
- The agent uses the flag shape from the CLI help, not the stale runbook.
