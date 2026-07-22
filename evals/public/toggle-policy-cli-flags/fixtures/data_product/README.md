# shipment-events-curated

Curated carrier shipment events for the demo tenant.

| Path | What it is |
|---|---|
| `spec.py` | Data-product spec (input, curated output port, hourly transform) |
| `contracts/shipment_events_output_quality.py` | Great Expectations contract enforced on the output port |
| `policies/create.sh` | Creates the contract and activates the data-quality policy |

Deployed by the `deploy-shipments` pipeline on merge to `main`, which runs
`policies/create.sh` for the target environment as part of the deploy.
