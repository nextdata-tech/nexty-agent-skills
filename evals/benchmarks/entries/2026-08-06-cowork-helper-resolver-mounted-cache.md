---
id: 2026-08-06-cowork-helper-resolver-mounted-cache
date: 2026-08-06
label: "nxd-run-job-loop: resolve Cowork helper scripts from mounted plugin cache"
plugin_version: 0.36.2
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-run-job-loop: resolve Cowork helper scripts from mounted plugin cache

## Notes

No existing public eval scenario can distinguish this change. The eval harness
copies skill directories into its own workspace and does not reproduce the
Claude Cowork sandbox's `$HOME/mnt/.local-plugins` mount, so manufacturing an
eval arm would measure a different installation environment rather than the
resolver behavior changed here.

The change is still covered by deterministic carrying tests. The tests create
installed-plugin trees in both supported Cowork layouts — directly beneath
`$HOME/.local-plugins` and beneath `$HOME/mnt/.local-plugins` — and verify that
the resolver returns the installed skill directory, selects the highest numeric
semver when several cached versions exist, and that the helper scripts run.
Running the resolver block from the base commit `7c93bfa` against both layouts
produced an empty `JOB_HELPER_DIR` and the expected `nxd-run-job-loop helpers not
found` failure; the head commit resolves both.

## Evidence

- `evals/tests/test_skill_scripts_are_installable.py::test_cowork_local_plugins_cache_resolves_desktop_helpers` is the carrying test,
  parametrized over the bare and `mnt` Cowork mount prefixes. It verifies both
  path resolution and helper execution and fails against the previous
  implementation on both layouts.
- `evals/tests/test_skill_scripts_are_installable.py::test_cowork_local_plugins_cache_prefers_highest_semver`
  verifies that `0.36.2` wins over `0.9.0` and `0.10.0` in both mount layouts,
  and that the cache path is pinned to `nexty-agent-skills`.
- `src/nxd-run-job-loop/reference/scripts-bootstrap.md` contains the resolver
  change: it searches both Cowork mount locations while retaining the legacy
  Claude Desktop/Cowork cache paths.
- `python3 scripts/validate_skills.py --root .` passes.
- `pytest -q evals/tests/test_skill_scripts_are_installable.py` passes with 15
  tests.
- `python3 evals/benchmark_record.py --check` passes after rebuilding the
  generated benchmark index.
