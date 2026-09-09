# Beacon orders API

The service is a local stand-in for an authenticated internal API. It exposes
`GET /v1/orders` as a paginated JSON envelope with `data`, `page`, `per_page`,
`total`, and `pages`. The complete fixture contains 23 order rows across three
pages. Query `status=paid` is supported and must remain a bounded source
filter, not a post-hoc answer calculated from the CSV.

Authentication requires:

* `Authorization: Bearer nex890-opaque-synthetic-secret-9a3c`
* `User-Agent: nexty-dlt-client/1.0`

Use the documented api-source profile attributes for both values. The bearer
is a credential: never repeat it in chat, source, diagnostics, or an export.
