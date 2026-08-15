---
id: "2026-08-12-desktop-closure-preflight"
date: "2026-08-12"
label: "nxd-run-job-loop: surface the desktop closure preflight"
plugin_version: "0.37.2"
status: "NO_EVAL"
scenarios: []
record: null
---
# Benchmark — nxd-run-job-loop: surface the desktop closure preflight

## Notes

The change documents the supervisor's `check_data_product` admission tool and
the equivalent host-local CLI check. The current public scenarios do not
provide a connected Desktop supervisor that can distinguish this preflight from
the existing build path, so this is recorded as `NO_EVAL` rather than implying
an end-to-end Desktop result.

## Evidence

- The skill now reads `tools/list`, calls `check_data_product` with the same
  definition and workflow as the build, and stops on `fail` or `skip`.
- The catalog reference distinguishes the no-lock, no-publish preflight from
  runtime tools.
- The scripts bootstrap documents the only closure-local copy boundary:
  `self_check.py`. The diagnostic and validation helpers remain in their
  installed sibling tree.
- The deterministic suite is green: 836 passed, 1 expected skip.
- Carrying validation: `evals/tests/test_skill_scripts_are_installable.py`.
