---
id: "2026-08-12-desktop-closure-preflight"
date: "2026-08-12"
label: "nxd-run-job-loop: surface the desktop closure preflight"
plugin_version: "0.37.3"
status: "NO_EVAL"
scenarios: []
record: null
---
# Benchmark — nxd-run-job-loop: surface the desktop closure preflight

## Notes

The change documents the supervisor's `check_data_product` admission tool and
the equivalent host-local CLI check, and adds bounded direct-CLI lifecycle
guidance. The local supervisor regressions pass, but the Claude-driven public
scenario did not produce a completed report after its endpoint shutdown, so this
remains `NO_EVAL` rather than implying a complete agent E2E result.

## Evidence

- The skill now reads `tools/list`, calls `check_data_product` with the same
  definition and workflow as the build, and stops on `fail` or `skip`.
- The catalog reference distinguishes the no-lock, no-publish preflight from
  runtime tools.
- The scripts bootstrap documents the only closure-local copy boundary:
  `self_check.py`. The diagnostic and validation helpers remain in their
  installed sibling tree.
- The deterministic suite is green: 839 passed, 1 warning.
- The NXD supervisor regression for a relative `--data-dir` publishes the
  Python fixture with `published=yes`; snapshot admission passes 2/2 and the
  MCP suite passes 48/48.
- A verifier regression was fixed so `sha256-v1:<digest>` definition IDs resolve
  to the persisted `definitions/sha256-v1/<digest>` directory.
- Carrying validation: `evals/tests/test_skill_scripts_are_installable.py`.
