---
id: 2026-09-01-nxd-generate-data-product-optional-empty-outputs
date: 2026-09-01
label: "nxd-generate-data-product: optional empty dlt outputs and aggregate count path"
plugin_version: 0.41.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-generate-data-product: optional empty dlt outputs and aggregate count path

## Notes

No existing public agent scenario distinguishes this change. The generator
scenario only exercises required physical models, while the available desktop
scenario coverage is either file-backed or requires a live supervisor. A new
agent arm would measure a different workflow instead of the self-check and
spec-registration contracts changed here, so this entry records `NO_EVAL`.

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
