# Terminal timeout and lifecycle truth

## Task for the agent

Use only the connected `mcp__nxd-desktop__*` tools for this terminal-only
workflow. The runner provides `ENDPOINT_URL` for a deterministic local REST
fixture with three pages; do not use a real provider or external network.

Use `terminal-timeout-lifecycle` as the workflow name for the product and all
of its lifecycle calls. Keep the same workflow and closure for the timeout,
inspection, retry, publication, resume, and cleanup evidence; use a distinct
workflow only for the intentionally broken failed-build copy.

Create a small closure that reads the fixture through the supported local
source path and run it through the public MCP lifecycle. The runner injects a
single client deadline for the first `build_data_product` request. Treat the
returned timeout as a client result, not as proof that the supervisor stopped.
Immediately call `inspect_run` and record the durable run id, terminal/continued
state, active stage, configured budget, request/page count, and retry count.

Then retry the same closure with a larger allowed budget or an explicitly
bounded source plan. Prove from `inspect_run` and the published listing that
the retry did not launch a duplicate build, that publication is atomic, and
that the same source semantics were preserved. Exercise and record distinct
public-MCP outcomes for timeout and failed build, and record the cleanup and
resume-first-versus-rebuild boundaries. The current public MCP catalog has no
cancellation operation, so do not invent one or substitute a private
supervisor command; runner/process cancellation is covered by the shared
stdio lifecycle harness. For the failed-build outcome, use a separate
deterministically broken copy/workflow, call `inspect_run` once, and show that
it never appears as published. Do not call a failed or unpublished run
successful.

All diagnostics must omit credentials and raw response bodies. Stop the
workflow through the public MCP surface and leave no process or temporary
state behind.

## Success checks

The withheld checker uses the runner-authored MCP trace, the loopback request
log, and structured `inspect_run`/publication evidence. It accepts only an
honest distinction between client timeout and supervisor lifecycle state; a
sleep, a direct supervisor CLI call, or a fabricated status record is not proof.
