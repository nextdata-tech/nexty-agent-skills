---
id: 2026-09-15-durable-pinned-nxd-artifact
date: 2026-09-15
label: "consume durable exact-source nxd artifacts"
plugin_version: 0.49.4
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — consume durable exact-source NXD artifacts

## Notes

No public DP scenario can distinguish artifact storage durability from the
agent's data-product behavior. The change is an integration-contract fix: an
exact pinned NXD source now resolves its immutable source-addressed release
asset before the expiring Actions-artifact fallback. The live CI failure that
motivated it is the missing artifact itself, not a scenario score.

## Evidence

- `evals/tests/test_nxd_artifact_action_contract.py` — verifies source-addressed
  release selection, release-target validation, manifest identity handling, and
  archive safety checks.
- `.github/actions/nxd-artifact/action.yaml` — verifies both durable and
  exact-source ephemeral resolution paths.
- Paired NXD producer work is in the durable source-addressed publisher and
  exact-SHA refresh workflow; no scenario fixture is changed here.
