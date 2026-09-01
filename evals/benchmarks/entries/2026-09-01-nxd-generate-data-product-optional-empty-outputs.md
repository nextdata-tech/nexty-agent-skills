---
id: 2026-09-01-nxd-generate-data-product-optional-empty-outputs
date: 2026-09-01
label: "nxd-generate-data-product: optional empty dlt outputs and aggregate count path"
plugin_version: 0.42.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-generate-data-product: optional empty dlt outputs and aggregate count path

## Notes

The opt-in Desktop E2E now covers the generated optional-output and aggregate
surface. It was exercised manually in a fresh Claude Desktop Cowork task with
the current `0.42.0` skill pack and the `nxd-desktop` connector. The entry
remains `NO_EVAL` because this was an acceptance run rather than a comparable
before/after benchmark arm, and the run did not produce a publishable result.

## Manual Desktop acceptance evidence — 2026-09-01

The task loaded `nxd-run-job-loop`, `nxd-build-semantic-data-product`, and
`nxd-generate-data-product` in order and authored the Python-only closure. The
native `check_data_product` preflight passed structure, runtime, contract, and
semantic stages. `build_data_product` then failed deterministically on both
attempts at `transform_error` / `child_reaped`: post-transform typed-output
normalization issued `DESCRIBE main.reviews` even though the explicitly
optional `reviews` model had no physical table. Publication therefore did not
issue an endpoint or bearer, so catalog discovery, the grouped aggregate query,
and endpoint teardown could not run. The task also could not execute the local
mapper demo because its Cowork sandbox had no `nxd` package; that boundary was
reported rather than treated as a pass.

This is runtime failure evidence for the follow-up supervisor fix, not a
passing eval result. The scenario remains registered and fail-closed until the
compatible runtime accepts absent optional outputs and the full publish/
describe/query lifecycle is rerun.

The static reader now resolves the standard `PHYSICAL_MODELS = BASE_MODELS +
DERIVED_MODELS` declaration; this removes one prior `unverified:` line and
turns the physical-model equality check on for template-shaped closures.
The change is carried by deterministic tests: an explicitly optional physical
model may have no dlt table, a non-empty optional model remains queryable, and a
missing required table still fails. The same tests reject optional metadata that
is not literal, is promised instead of catalog-registered, or is omitted from
the output model chain. The documentation also defines the governed COUNT
metric shape for aggregate-only products and the unavailable behavior of a
semantic view whose optional physical table is absent.

## Evidence

`evals/tests/test_self_check_queryability_and_phase_gates.py` covers the
optional-output and semantic-registration contract when run locally with real
`dlt[duckdb]==1.28.2` plus pandas. The repository CI recipe does not install
those two packages, so the three executable dlt cases skip there; the
structural cases remain covered in CI:

- `test_zero_row_optional_output_may_be_absent`
- `test_non_empty_optional_output_is_queryable`
- `test_required_zero_row_output_still_has_specific_missing_table_diagnostic`
- `test_optional_metadata_requires_a_literal_physical_model_registration`
- `test_optional_metadata_cannot_name_a_semantic_view`
- `test_optional_metadata_cannot_be_promised`
- `test_optional_metadata_requires_catalog_registration`
- `test_semantic_view_cannot_be_promised`

`evals/tests/test_spec_api_compiler_rules.py` carries the aggregate-only
COUNT guidance, and `evals/tests/test_dp_diagnostics_schema.py` keeps the new
diagnostic codes in the registry contract.
