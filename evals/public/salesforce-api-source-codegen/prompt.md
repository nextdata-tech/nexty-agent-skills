# Scenario: Generate a Salesforce REST data-product source

The workspace contains `source-contract.yaml`, a pinned synthetic Salesforce
contract. It describes one read-only SOQL query, the `records` response
envelope, and a `nextRecordsUrl` continuation. The eval is local-only: do not
contact Salesforce or any other external service.

## Task

Read `source-contract.yaml` before authoring. Create a Python-only local
desktop data-product closure at the workspace root with:

- `spec.py`
- `models.py`
- `infra-profile.yaml`
- `transform/main.py`
- `connectivity_check.py`
- `requirements.txt`
- `README.md`
- `.gitignore`
- `SENSITIVE`

Use the Salesforce recipe from the installed `nxd-generate-data-product`
skill. Build ingestion with dlt `RESTAPIConfig` and `rest_api_resources`.
Read the configured SOQL from `secrets`, select the `records` array, and follow
the configured `nextRecordsUrl` response link with dlt pagination. Flatten the
promised account fields before landing them through the local DuckDB pipeline.

Keep `source_kind`, instance/base URL, query, endpoint, auth type, and required
scope in flat `api-source` attributes. Assemble bearer auth from `secrets`;
the synthetic token belongs only in `infra-profile.yaml`. This source is
read-only: do not add Salesforce create/update/delete operations or a raw HTTP
client. Do not run dlt or the provider probe; a static syntax check is
sufficient.

## Eval boundary

The evaluator checks the generated closure statically. It does not provide a
Salesforce server and it does not contact Salesforce.
