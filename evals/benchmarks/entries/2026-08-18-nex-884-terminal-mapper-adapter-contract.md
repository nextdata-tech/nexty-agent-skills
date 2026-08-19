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

The entry remains `NO_EVAL` for benchmark purposes because no pre-change arm exists: this scenario was introduced by this change, so a before/after comparison would manufacture a baseline. The first authenticated live acceptance arm now passes with the runner-owned stdio MCP path: Claude Code used the isolated server, passed self-check, built through synthetic approval, inspected the terminal run, and the deterministic checker passed both public-adapter-only and redacted-MCP-trace checks. The run used Sonnet for a 28-turn/27-tool-call acceptance check; no production credential or provider payload was used. This is acceptance evidence, not a comparative benchmark number.

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
