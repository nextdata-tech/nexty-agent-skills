# Terminal mapper-adapter evaluator — runner-owned stdio MCP

This scenario is registered with the normal terminal evaluator
(`evals/run.py`) and uses the runner-authored `runner_mcp` trace. The agent
receives only a private, strict MCP config for one isolated
`nxd-desktop-supervisor` process. The deterministic checker receives the
redacted JSON-RPC trace from the proxy, not text printed by the agent.

The runner-side fixtures provide a synthetic, recorded provider and an
evaluation-only approval profile. They are outside the agent workspace,
read-only, and never use a real provider credential. The closure must use the
public `make_call` adapter injected into `map_inputs`; direct SDK/private
transport imports, fabricated approval, and raw provider responses fail the
checker. The recorded response sequence covers a schema-invalid response, a
correction/retry, and an optional absent value.

The harness separately reports setup, agent, and server/provider outcomes. It
uses `--strict-mcp-config`, an allowlist for the `nxd-desktop` tool namespace,
runner-owned state/trace/profile paths, process-group cleanup, and
value-aware redaction. A real Claude authentication and the feature-gated NXD
evaluation binary are required for a live cell; missing authentication or
loopback permission is an infrastructure error, not a passing or failing
mapper result.

The checker deliberately rejects a plain transcript as the MCP trace. This
prevents an agent from satisfying the MCP requirement by printing tool names
and keeps the approval/provider boundary in the supervisor harness.
