# Policy runbook (customer-profiles-curated)

Copied from the Commerce team's wiki page "Adding a policy", last edited
2025-11-04. Nobody has re-run this since the CLI was upgraded, so double-check
the flags against the CLI before using it.

## Turning on a sensitivity policy

```bash
nxd activate policy \
  --name <policy-name> \
  --policy user/SensitivityCompliance \
  --validation-url ./contracts/sensitivity_rules.py \
  --create-contract \
  --consequence STOP
```

The `--create-contract` flag uploads the contract code and switches the policy
on in a single step, so there is nothing to register beforehand.

## Checking it worked

```bash
nxd ls data-product policies --name <policy-name>
```
