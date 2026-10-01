# Synthetic provider enrollment DP

This spec backs the public `semantic-filter-coverage` scenario. It contains only
generated patient IDs, nonnumeric synthetic provider keys, and fabricated
product, region, territory, and enrollment values. It does not represent a
customer dataset or real provider NPIs.

The DP exposes three semantic models: `patient_enrollment` (fact grain),
`patient_provider` (one row per synthetic patient, carrying the treating provider's specialty and territory), and
`enrollment_metrics` (a semantic view over the fact). The fact joins to
`patient_provider` as many-to-one on `PATIENT_ID`. It is keyed by patient because the
semantic compiler rejects a `COUNT_DISTINCT` of a non-grain column across a join unless
that column is the join key. `enrolled_patients` is a distinct
patient count whose definition includes `PERIOD_TYPE = 'DAILY'`; weekly-only
synthetic patients make that definition observable. `ALL` is a per-patient
product rollup row, alongside the individual product rows.

The Snowflake output uses the data-product-scoped schema supplied to the
transform by NXD. The transform truncates and refills the platform-provisioned staging tables
(`snowflake.full_table_name(<model>)`); writing to the final table names is
silently overwritten when promotion swaps the empty staging tables in.
Re-running is deterministic and idempotent.

`spec.py` follows the current `nxd.spec` semantic DSL: base tables are promised,
the metric view is registered with `.model(...)`, and `.semantic_tools()`
generates the MCP tools. The first `nxd launch` can fail produce-verification
because the promised tables are seeded by the transform after that check; the
operator script retries once so the second launch verifies the seeded tables.
