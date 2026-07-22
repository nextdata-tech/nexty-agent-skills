# Session context

## Mesh

`nxd-setup` already ran this session and selected the mesh `logistics-prod`.
It wrote the session config to:

```
/tmp/nxd-logistics-prod.yaml
```

`nxd whoami` against that config reports `ops-oncall@example-logistics.com`.
The mesh hosts two environments, `staging` and `demo`. The demo tenant that
sales is presenting to is served from the `demo` environment.

## Repo

The data product lives in this workspace under `data_product/`. It is
deployed from the `deploy-shipments` pipeline, which runs on merge to `main`.

## What the requester told us

Sales is running a walkthrough on the `demo` environment in about an hour and
the STOP-consequence data-quality policy on `shipment-events-curated` is
blocking the sample dataset they want to show. They want it off for the
walkthrough and back on immediately afterwards, with the contract left intact
so nothing has to be rebuilt.

The oncall engineer who picked this up has never toggled a policy before and
found `docs/legacy-policy-runbook.md` in the wiki export. They want a runbook
they can paste command-by-command, not a description.
