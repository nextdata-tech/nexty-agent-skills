# Terminal timeout and lifecycle truth evaluator

This terminal-only scenario drives the public `nxd-desktop` MCP tools over the
runner-owned stdio session while a deterministic, paginated REST fixture runs
on loopback. The runner injects one bounded client deadline for the first
`build_data_product` request, keeps the child server alive for the late reply,
and captures a redacted JSON-RPC trace. The withheld checker treats durable
`inspect_run` records and published-product listings as the authority rather
than trusting the agent's narration.

The scenario covers a caller-configured timeout, a larger-budget retry after
that run is terminal, a bounded plan using the runtime default, publication
atomicity, and resume-first recovery. It deliberately does not claim a live
Desktop UI/provider run. The current public MCP catalog has no cancellation
operation; cancellation is therefore kept as a runner/process-lifecycle
boundary and is covered by the shared stdio cleanup tests, rather than being
invented as a private supervisor command. A client-abandonment race still needs
a second concurrent MCP client, which the current per-cell harness does not
expose.
