# Terminal self-check and closure provenance evaluator

This scenario exercises the supported `check_data_product` MCP tool from a
terminal-only isolated Claude session. The runner starts one per-cell
`nxd-desktop-supervisor` over stdio, captures a runner-authored redacted JSON-RPC
trace, and uses the same synthetic evaluation profile as the terminal mapper
scenario. The agent never receives the profile, provider responses, or checker.

The authoritative oracle checks the public trace and the closure mutations the
agent submitted: a positive four-stage report with pinned definition and
runtime provenance; distinct malformed/missing/import/transform/helper
diagnostics; and changed content IDs after an authoring mutation. A missing or
skipped check is never promoted to pass. The checker is deterministic and is
run separately from the LLM judge.

This is a terminal scenario, not a direct Python unit test. It needs an
authenticated Claude CLI, the isolated stdio harness, and an NXD supervisor
built with the runner-only synthetic evaluation profile. No real provider or
credential is used.
