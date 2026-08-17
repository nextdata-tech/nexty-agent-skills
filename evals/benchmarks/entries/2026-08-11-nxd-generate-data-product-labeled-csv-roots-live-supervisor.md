---
id: "2026-08-11-nxd-generate-data-product-labeled-csv-roots-live-supervisor"
date: "2026-08-11"
label: "nxd-generate-data-product: labeled csv roots live supervisor boundary"
plugin_version: "0.36.8"
status: "NO_EVAL"
scenarios: []
record: null
---
# Benchmark — nxd-generate-data-product: labeled csv roots live supervisor boundary

## Notes

The live supervisor scenario exists at
`evals/public/multi-source-labeled-roots-supervisor/`, but this workstation has
no compatible `EVAL_DESKTOP_SUPERVISOR_DIR` and `EVAL_DESKTOP_PYTHON` runtime.
No publication or published-row result is claimed; the runtime-free structural
scenario is measured separately.

## Evidence

The opt-in scenario's setup and prerequisites are documented in
[`evals/public/multi-source-labeled-roots-supervisor/README.md`](../../public/multi-source-labeled-roots-supervisor/README.md).
The carrying contract is covered by `evals/tests/test_labeled_root_checkers.py`,
including pinned-root and mutation negative cases.
