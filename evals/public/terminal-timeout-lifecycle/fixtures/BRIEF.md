# Slow paginated local source

The local service exposes `GET /v1/events` as a JSON envelope with `data`,
`page`, `per_page`, `total`, and `pages`. It contains 23 synthetic events over
three pages. Every request requires `Authorization: Bearer
nex888-opaque-synthetic-secret-2d4c`. The bearer is only a fixture credential;
do not repeat it in chat, source, or diagnostics.
