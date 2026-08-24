---
id: 2026-08-24-linear-source-reference
date: 2026-08-24
label: "nxd-generate-data-product: Linear connector reference"
plugin_version: 0.38.3
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-generate-data-product: Linear connector reference

## Notes

No public scenario builds against Linear, and none could without a workspace
and a personal key — the existing api-source scenarios drive a local stub. So
no arm can distinguish this change, and manufacturing one would mean a live
third-party credential in CI, which the suite deliberately avoids.

The reference exists because `api-source.md` covers GraphQL over the dlt REST
connector *generically*, and roughly half of what a Linear closure needs is not
generic. Each fact below was rediscovered by failing, while building a closure
that fetched a live project, judged its open tickets in-transform and published:

- A personal key is `auth_type: api_key` with `auth_key_name: Authorization`.
  Choosing `bearer` because the credential is a token sends
  `Authorization: Bearer …`, which Linear rejects.
- `eqIgnoreCase` matches the whole value, so a project displayed as
  `Nexty Pocket` is not matched by `pocket`. It fails as an empty result with a
  valid credential, a valid query and a `200` — which reads as a connector or
  credential problem and surfaces much later as an empty promised model. This
  one cost a full build cycle.
- Open-ness is a state TYPE (`backlog` / `unstarted` / `started`), not a state
  name; names are author-defined per team and rename freely.
- List fields such as `labels { nodes { name } }` land as dlt child tables and
  fail the read-back assert, while scalar-nested fields such as
  `state { name type }` flatten harmlessly. The rule is about lists, not
  nesting.
- `priority` runs 1 = urgent to 4 = low with 0 meaning "not set", so ordering
  ascending puts unset first — and 23 of 26 open tickets in the observed project
  were 0, which makes "where do we disagree with Linear's priority?" nearly
  unanswerable there.

## Evidence

`evals/tests/test_linear_source_reference.py`, seven tests.

Six assert the documented contract and run everywhere including CI. Verified
non-vacuous by removing the reference: six of the seven fail without it.

The seventh is the one claim whose truth lives in another package. It builds the
published config — the POST body, the API-key auth block, `cursor_body_path` and
the `data.<root>.pageInfo` paginator paths — against the pinned
`dlt[duckdb]==1.28.2` and asserts the resource list is produced. No request is
made, so it needs no Linear key and no network beyond resolving the pin. If a
dlt bump stops accepting that shape, every Linear closure breaks while the doc
still reads correctly; this fails first.
