---
id: 2026-08-18-nex-884-terminal-mapper-adapter-contract
date: 2026-08-18
label: "NEX-884: terminal field-mapper adapter contract scenario"
plugin_version: 0.37.4
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — NEX-884 terminal field-mapper adapter contract scenario

## Notes

This remains `NO_EVAL`: the change now includes the runner-owned stdio MCP
harness and a public scenario, but a valid before/after agent arm was not
obtained in this environment. The local run reached the isolated MCP proxy
and recorded setup/JSON-RPC activity, then stopped at the Claude CLI
authentication boundary (`Not logged in`). A direct supervisor probe also
reached initialize/tools-list but could not bind the loopback approval surface
inside the restricted test sandbox. Neither condition is a mapper verdict, so
no benchmark number is recorded. Re-run with an authenticated Claude CLI and
loopback permission before claiming NEX-884 complete.

## Evidence

- `evals/desktop_stdio.py` — strict per-cell MCP config, proxy trace,
  credential-isolated child environment, redaction, and process cleanup.
- `evals/run.py` — scenario marker, runner-owned profile preparation, MCP trace
  plumbing, and setup/agent/server outcome separation.
- `evals/tests/test_desktop_stdio.py` — fake-child forwarding, redaction,
  credential isolation, strict tool flags, and cleanup tests.
- `evals/tests/test_terminal_field_mapper_adapter_contract.py` — public adapter
  execution, checker alias/negative cases, trace-authorship, and redaction
  regressions.
- `evals/tests/test_deterministic_check.py` — nonempty runner trace acceptance
  and empty-trace fail-closed behavior.
- `evals/public/terminal-field-mapper-adapter-contract/fixtures/prepare_stdio_profile.py`
  — runner-only recorded-provider/approval profile materializer.
