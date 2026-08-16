# Terminal mapper-adapter evaluator — required runner capability

This scenario is registered with the normal terminal evaluator (`evals/run.py`)
so it receives the agent transcript and its deterministic checker receives that
trace. It intentionally does not claim to be runnable today.

The present runner has two adjacent but insufficient paths:

- `fixtures/desktop.json` provisions `nxd-desktop-supervisor` CLI binaries,
  then guards supervisor process cleanup. It does not launch the `nxd-desktop`
  MCP server or make its tools available to the agent.
- `fixtures/mcp.json` launches only the semantic HTTP fixture; the Inspect
  stdio spike similarly launches only `stub_semantic_server.py`. Neither can
  inject a mapper provider or exercise the build/admission MCP tools.

To enable this scenario, add a runner capability that, for each cell:

1. starts `nxd-desktop` as a stdio MCP child with isolated data/run directories;
2. injects the recorded mapper provider and one synthetic secret without adding
   either to the agent workspace or environment;
3. exposes the public MCP tools to the terminal agent and records redacted
   JSON-RPC request/response events; and
4. classifies setup, provider, and agent timeout/termination independently,
   then stops the process group and removes all run, trace, and credential
   state in every exit path.

Until that capability exists, `ci_skip` is deliberate and explicit. The
non-skipped unit tests in `evals/tests/test_terminal_field_mapper_adapter_contract.py`
continue to exercise the public adapter with synthetic local fixtures against a
canonical NXD checkout; they are not offered as a substitute for this MCP E2E.
