# Scenario: Generate a Jira REST data-product source

The workspace contains `source-contract.yaml`, a pinned synthetic Jira
Cloud-style contract. It describes a read-only issue search, its JQL and
offset pagination, and the nested fields that must become flat landing
columns. The eval is local-only: do not contact Jira or any other external
service.

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

Use the Jira recipe from the installed `nxd-generate-data-product` skill.
Build ingestion with dlt `RESTAPIConfig` and `rest_api_resources`. Read the
configured JQL, `startAt`, and `maxResults` from `secrets`, select the
top-level `issues` array, paginate until `total`, and flatten the declared
`fields` into flat scalar columns before landing them through local DuckDB.

Keep `source_kind`, base URL, endpoint, JQL, pagination settings, auth type,
and username in flat `api-source` attributes. Assemble HTTP basic auth from
`secrets`; the synthetic API token belongs only in `infra-profile.yaml`. This
source is read-only: do not add issue creation, update, transition,
attachment, or permission operations, and do not use a raw HTTP client. Do
not run dlt or the provider probe; a static syntax check is sufficient.

## Eval boundary

The evaluator checks the generated closure statically. It does not provide a
Jira server and it does not contact Jira.
