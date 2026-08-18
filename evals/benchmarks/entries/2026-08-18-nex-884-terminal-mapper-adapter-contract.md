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

This is `NO_EVAL`: the PR adds a public terminal scenario and deterministic
adapter/checker coverage, but the scenario remains `ci_skip` until the
runner-owned `nxd-desktop` stdio MCP capability, synthetic provider injection,
and runner-authored redacted JSON-RPC trace are available. There is no valid
before/after agent arm yet; running the generic terminal evaluator would only
grade the existing transcript path and would manufacture evidence for the new
MCP contract.

## Evidence

The marker-file plumbing is covered by unit tests but is not exercised by a
live checker invocation while the runner exits before checker launch; the
future stdio harness must cover that path end to end.

- `evals/tests/test_terminal_field_mapper_adapter_contract.py` — canonical
  adapter execution with synthetic fixtures, checker alias/negative cases,
  trace-authorship and redaction regressions.
- `evals/tests/test_deterministic_check.py` — runner marker-file isolation and
  fail-closed trace-source wiring.
- `evals/public/terminal-field-mapper-adapter-contract/README.md` — explicit
  capability contract and current `ci_skip` boundary.
