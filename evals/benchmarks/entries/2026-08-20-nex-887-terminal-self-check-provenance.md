---
id: "2026-08-20-nex-887-terminal-self-check-provenance"
date: "2026-08-20"
label: "NEX-887: terminal self-check and closure provenance"
plugin_version: "0.37.4"
status: "PASS"
scenarios:
  - "terminal-self-check-provenance"
record: "../records/2026-08-20-nex-887-terminal-self-check-provenance.json"
---
# Benchmark — NEX-887: terminal self-check and closure provenance

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| current_pack | current_pack | terminal-self-check-provenance | PASS | 5/5 | 20 | 19 | 12952 | 1.01 | claude-opus-4-8 |

## Notes

Fresh authenticated local acceptance run against the isolated stdio MCP supervisor and synthetic NXD profile. This is acceptance evidence for a new scenario, not a before/after benchmark; the scenario is ci_skip in hosted CI because that runtime is not provisioned.

## Evidence

Compact report: [`../records/2026-08-20-nex-887-terminal-self-check-provenance.json`](../records/2026-08-20-nex-887-terminal-self-check-provenance.json)
