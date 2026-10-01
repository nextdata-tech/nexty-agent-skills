---
id: "2026-10-01-mcp-localhost-opt-in"
date: "2026-10-01"
label: "local semantic MCP transport and loopback opt-in"
plugin_version: "0.54.11"
status: "NO_EVAL"
scenarios: []
record: null
---
# Benchmark — local semantic MCP transport and loopback opt-in

## Notes

No public agent scenario distinguishes this transport/test-harness fix. Customer
behavior is unchanged unless `NXD_MCP_ALLOW_HTTP_LOCALHOST=1`, which only the
eval harness sets for `127.0.0.1`; the opt-in allows HTTP to the local fixture
gateway while remote HTTP endpoints continue to upgrade to HTTPS.

## Evidence

- `evals/tests/test_local_mesh_runner.py` — matched-interpreter fixture-server
  smoke test covers authenticated gateway preflight, discovery, semantic tool
  listing, and a real `list_models` MCP call over the local proxy.
- `evals/tests/test_local_mesh_runner.py` — endpoint normalization coverage
  confirms only exact IPv4/IPv6 loopback literals retain HTTP under opt-in.
