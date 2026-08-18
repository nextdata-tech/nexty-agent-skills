# Terminal mapper-adapter evaluator — required runner capability

This scenario is registered with the normal terminal evaluator (`evals/run.py`)
with an explicit `runner_mcp` trace source. The deterministic checker must
receive runner-authored JSONL MCP events, never the agent transcript; the
current generic runner fails closed until the stdio capability exists. It
intentionally does not claim to be runnable today.

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
   JSONL events with `source: runner`, `protocol: mcp`, method, and tool fields;
   the synthetic secret is supplied through a runner-owned private file; and
4. classifies setup, provider, and agent timeout/termination independently,
   then stops the process group and removes all run, trace, and credential
   state in every exit path.

Until that capability exists, `ci_skip` is deliberate and explicit. The
non-skipped unit tests in `evals/tests/test_terminal_field_mapper_adapter_contract.py`
continue to exercise the public adapter with synthetic local fixtures against a
canonical NXD checkout; they are not offered as a substitute for this MCP E2E.

The checker deliberately rejects plain transcript text as a trace. This keeps
an agent from satisfying the MCP requirement by printing tool names, and makes
the missing runner capability an infrastructure failure rather than a false
agent pass.
