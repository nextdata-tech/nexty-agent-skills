---
id: 2026-08-19-api-source-graphql-post-body
date: 2026-08-19
label: "nxd-generate-data-product: POSTed-JSON-body api-source closures, and groupable keys"
plugin_version: 0.37.5
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-generate-data-product: POSTed-JSON-body api-source closures, and groupable keys

## Notes

No public scenario builds an api-source closure against a GraphQL endpoint. The
existing api-source scenarios drive GET resources against a local stub, so none
of the five defects this change fixes can appear in them: the expression
collision needs braces in a POSTed body, the staging finding needs an api
closure that also carries `data/`, the `BASE_MODELS` conflict needs both a
fetched model and a landed reference model in one closure, and the probe
defects need a probe invoked by absolute path against a filter that matches
nothing. Manufacturing a GraphQL scenario would measure a new connector arm
rather than provide a trustworthy before/after on this change.

All four were observed in one live build (a Linear closure over project
`Nexty Pocket`), each as a failure whose message pointed away from its cause:

- `ValueError: Expression ... defined in 'json' is not valid` named
  `resources`, not the GraphQL body it was scanning.
- `structure/definition_files_missing: snapshot missing csv-source-path`
  mentioned neither `data/` nor the connector type, and arrived before any
  Python ran.
- `struct.base_models_vs_data_dirs` fired on a closure following the
  reference's own "Landed reference data in an API closure" instructions.
- The probe printed `OK — 0 node(s)` and was read as a pass, so the build was
  launched against a filter that matched nothing.
- A fifth defect surfaced only after the product was serving and had no error
  at all: every model key was `field(string(), primary_key())`, copied from the
  worked example, and a key with only the key role is not groupable. The
  product answered counts and could not answer which tickets they were.
  `describe_models` simply omits the column, so the gap reads as a missing
  question rather than a missing role.

## Evidence

`evals/tests/test_api_source_graphql_body_contract.py` carries the change. It
defines **twelve** tests. Eleven assert the documented contract and were each
verified to fail against the previous revisions of the files they cover —
`reference/api-source.md`, `reference/derived-models.md`, `SKILL.md`,
`reference/models-example.md`, `reference/nxd-spec-api.md`, the
`nxd-build-semantic-data-product` role grammar and templates, and
`scripts/self_check.py` — and to pass after them.

The twelfth is the one assertion whose truth lives outside this repo: it runs
the pinned `dlt[duckdb]==1.28.2` in a subprocess and proves that a
brace-doubled GraphQL body carries no dlt expressions, that the unescaped body
still trips the scanner, and that `expand_placeholders` collapses the escape
back to the byte-identical query before the request — so a dlt bump that broke
the round-trip would fail here rather than silently posting doubled braces. It
resolves that pin from the network on a cold `uv` cache, which is the one place
this suite reaches outside the repo.

Three of the twelve cover the key-role defect specifically: a spelling-independent
scan for a bare `primary_key()` across all THREE skills that teach this DSL —
the placing skill, the inferring skill, and the platform skill, since the
`describe_models` consequence is not desktop-specific — plus a check that the
inference skill's own grammar and templates teach the pairing, and a check that
`self_check.py` reports `struct.key_not_groupable` as a warning. That warning is
the mechanical backstop: the defect has no error, no failed assert and no
missing table to catch it, so documentation alone would not stop it recurring.
Its code is registered in `dp_diagnostics.CODES` so the shared vocabulary and
the checker cannot drift apart. The scan skips the vendored
`nextdata-public-examples` submodule, which is upstream.

`evals/tests/test_api_source_header_contract.py` and
`evals/tests/test_api_source_connector_gate.py` continue to cover the GET-side
recipe this change leaves unaltered.
