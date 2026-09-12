# Terminal timeout and lifecycle truth evaluator

This terminal-only scenario drives the public `nxd-desktop` MCP tools over the
runner-owned stdio session while a deterministic, paginated REST fixture runs
on loopback. The runner injects one bounded client deadline for the first
`build_data_product` request, keeps the child server alive for the late reply,
and captures a redacted JSON-RPC trace. The withheld checker treats durable
`inspect_run` records and published-product listings as the authority rather
than trusting the agent's narration.

The scenario covers a caller-configured timeout, a bounded retry only when the
timed-out run is not already published, publication atomicity, and resume-first
recovery when it is. The paginated fixture fixes its page size so a single
request cannot collapse the source evidence. It deliberately does not claim a live
Desktop UI/provider run. The current public MCP catalog has no cancellation
operation; cancellation is therefore kept as a runner/process-lifecycle
boundary and is covered by the shared stdio cleanup tests, rather than being
invented as a private supervisor command. A client-abandonment race still needs
a second concurrent MCP client, which the current per-cell harness does not
expose.

One deliberate limit in `redaction-and-cleanup`: only the injected credential
is marker-scanned. A raw-response-body canary is not, because the scan cannot
separate a legitimately materialized payload — an API source may land the raw
envelope by design — or a passively observed tool result from a real leak, so
it could only manufacture false failures. That half of the check is graded from
the trace and structured evidence by the judge.
