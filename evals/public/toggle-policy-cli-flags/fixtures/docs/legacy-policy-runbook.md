# Policy Toggle Runbook (internal wiki export)

_Last edited 14 months ago. Exported from the team wiki._

Used by the platform team when a policy has to come off a data product for a
customer demo and go back on afterwards.

## List the policies on a data product

```bash
nxd data-product policies --name <dp-name> --env <env>
```

## Take the policy off

```bash
nxd deactivate policy --name <policy-name> --env <env>
```

Deactivation is scoped to the environment you pass, so always pass `--env` to
avoid taking the policy off in prod by accident.

## Put the policy back

```bash
nxd activate policy --name <policy-name>
```

Reactivation restores whatever configuration the policy had before it was
deactivated, so no other flags are needed.

## Notes

- If a policy needs to be gone for good, deactivating is enough — there is
  nothing else to clean up.
- Once the policy is back on, the toggle is done.
