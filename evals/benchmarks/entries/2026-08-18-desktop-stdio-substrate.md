---
id: 2026-08-18-desktop-stdio-substrate
date: 2026-08-18
label: "evals: isolated Desktop stdio MCP substrate"
plugin_version: 0.37.4
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — isolated Desktop stdio MCP substrate

## Notes

This is `NO_EVAL` because the change adds runner-owned Desktop stdio
infrastructure, but no public scenario is wired through `evals/run.py` to
exercise that path at this commit. There is therefore no valid before/after
agent arm: running a model benchmark would measure the existing runner path,
not the new substrate, and would manufacture evidence. The follow-up scenario
and NXD evaluation-profile work will own the first runnable end-to-end arm.

The deterministic harness tests still cover the changed behavior directly:
MCP proxy forwarding, process-group cleanup, redaction, private file modes,
default tool allowlisting, and concurrent trace writes.

## Evidence

- `evals/tests/test_desktop_stdio.py` — fake-child JSON-RPC forwarding,
  cleanup, redaction, file permissions, allowlist, and concurrent trace tests.
- `evals/tests/test_multi_turn_driver.py` — existing backend lifecycle
  regression coverage run alongside the substrate tests.
