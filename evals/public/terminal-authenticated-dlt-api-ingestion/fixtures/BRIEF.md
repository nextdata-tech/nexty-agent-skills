# Beacon orders API

The service is a local stand-in for an authenticated internal API. It exposes
`GET /v1/orders` as a paginated JSON envelope with `data`, `page`, `per_page`,
`total`, and `pages`. The complete fixture contains 23 order rows across three
pages. Query `status=paid` is supported and must remain a bounded source
filter, not a post-hoc answer calculated from the CSV.

The runner injects the bearer through `NXD_EVAL_SOURCE_TOKEN`. Read that
environment variable when authoring the runtime profile; never print, quote,
or copy its value into source, the companion topology file, diagnostics, or
your response. The service also requires this non-secret header:

* `User-Agent: nexty-dlt-client/1.0`

Use the documented api-source profile attributes for the bearer and header.
