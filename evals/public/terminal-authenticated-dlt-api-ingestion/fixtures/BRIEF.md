# Beacon orders API

The service is a local stand-in for an authenticated internal API. It exposes
`GET /v1/orders` as a paginated JSON envelope with `data`, `page`, `per_page`,
`total`, and `pages`. The complete fixture contains 23 order rows across three
pages. Query `status=paid` is supported and must remain a bounded source
filter, not a post-hoc answer calculated from the CSV.

Configure the `api-source` entry in `infra-profile.yaml` with `base_url` set
to the runner-provided URL in `ENDPOINT_URL` and `endpoint_orders` set to the
relative path `/v1/orders`. `endpoint_orders` is a path, not a complete URL;
do not add an endpoint companion file. Set `auth_type: bearer` for the
positive case. The public credential setting is
`credential_env: NXD_EVAL_SOURCE_TOKEN`; the trusted runtime resolves it from
that named environment variable. The transform must access the value through
`os.environ[secrets["credential_env"]]`. Never inspect environment variables
or print, quote, copy, or embed credential values in source, profiles,
command arguments, diagnostics, or your response.

The required public header is:

* `User-Agent: nexty-dlt-client/1.0`

Use the DLT REST connector and the documented api-source profile attributes.

For this evaluation, source requests must come only from the DLT transform
during each workflow's `validation` or the positive `start_run`. The
fixture credential is available only inside the trusted runtime, and requests
outside those windows invalidate the evidence. This is a task-specific
exception to the general api-source standalone `connectivity_check.py`
payload-probe step: do not create or run that probe, or any other direct HTTP
helper. Use DLT response evidence in the required workflow runs to verify the
response shape and pagination; do not claim an additional payload check.
