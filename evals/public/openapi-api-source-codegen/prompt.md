# Scenario: Generate a REST API data-product source from OpenAPI

The workspace contains `openapi.yaml`, a synthetic OpenAPI 3.0 contract for a
read-only orders endpoint. The contract declares its server, route, response
envelope and bearer scheme. Its `x-nexty-required-scopes` extension documents
the mock authorization requirement `orders:read` (the OpenAPI 3.0 bearer
security requirement has an empty scope list). It also uses the
`x-nexty-pagination` extension to make the API's cursor semantics explicit;
OpenAPI does not standardize pagination.

## Task

Read `openapi.yaml` before authoring. Use the generic REST API recipe in the
installed `nxd-generate-data-product` skill and its `reference/source-types.md`
index to locate `reference/api-source.md`. Create a Python-only local Desktop
data-product closure with:

- `spec.py`
- `models.py`
- `infra-profile.yaml`
- `transform/main.py`
- `connectivity_check.py`
- `requirements.txt`
- `README.md`
- `.gitignore`
- `SENSITIVE`

The contract has one operation, so declare one explicit `orders` resource in
the `RESTAPIConfig` passed to `rest_api_resources`. Build ingestion with dlt
`RESTAPIConfig` and `rest_api_resources`. Use the
contract's server and `/orders` route through the flat `base_url` and
`endpoint_orders` profile attributes; select the `results` envelope and follow
`next_cursor` through the `after` query parameter with an explicit cursor
paginator. Keep the source read-only: only the documented GET operation belongs
in the generated resource.

Declare bearer auth in flat `api-source` profile attributes, dispatching from
`secrets["auth_type"]` and reading the credential from the private
`auth_token` attribute. Add a non-secret `required_scopes` profile attribute
with the exact scope strings from the contract extension; it documents the
authorization requirement and is not sent as an HTTP credential. Dispatch
bearer auth in the positive `auth_type == "bearer"` branch, reject unsupported
auth types, then build and call the REST config after the dispatch. No credential
was supplied for this scenario: use exactly the clearly marked, non-usable
profile placeholder `${ORDERS_READ_TOKEN}` (the checker permits this placeholder
in documentation; do not substitute another value). Mark `base_url`,
`endpoint_orders`, `auth_type`, and
`required_scopes` public; keep `auth_token` private. Do not invent a token, copy
one into generated source, or claim the closure has authenticated successfully.
Keep the profile marked sensitive and state that a real credential must be
supplied locally before a later connectivity check.

This is a static generation eval. Do not install packages, run dlt, materialize
the product, execute `connectivity_check.py`, probe the endpoint, or contact an
external service. The hostname is synthetic and is not reachable. Do not
create deployment manifests or generated build outputs.

## Eval boundary

The runner checks generated artifacts structurally. Separate local unit tests
exercise the OpenAPI compiler, mock authorization and cursor pagination, but
they do not execute the agent-generated dlt code. The scenario makes no claim
that a provider connection or Desktop end-to-end build was tested.
