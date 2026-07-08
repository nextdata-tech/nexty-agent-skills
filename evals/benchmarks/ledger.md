# Skill benchmark ledger

Append-only history of measured skill changes: for every skill improvement,
the before/after eval verdicts and efficiency metrics (turns, tool calls,
tokens, cost) that justified shipping it. Entries are appended by
`evals/benchmark_record.py` from `run.py --report` JSONs; the matching compact
reports live in `records/`. Newest entries at the bottom.

Reading a row: the judge verdict (checks passed) is the regression gate;
turns/tool_calls/tokens are the efficiency trend. Single-run metric deltas
under ~20% are noise — see "Benchmarking a skill change" in `evals/README.md`.

## 2026-07-06 — nxd-setup: sandboxed-shell headless device-flow branch (plugin v0.8.0)

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| before-v0.7.0 | current_pack | nxd-setup-headless-auth | FAIL | 3/8 | 4 | 2 | 8120 | 0.29 | sonnet |
| after-v0.8.0 | no_skills | nxd-setup-headless-auth | FAIL | 4/8 | 7 | 6 | 19724 | 0.73 | sonnet |
| after-v0.8.0 | current_pack | nxd-setup-headless-auth | PASS | 8/8 | 1 | 4 | 54 | 0.45 | sonnet |

Notes: Fix from a Cowork session debrief: interactive 'nxd login' cannot survive a per-call sandbox process tree. v0.8.0 adds a Step-4 sandboxed-shell branch + reference/headless-device-flow.md (manual curl device flow, pkce_verifier round-trip, hand-written tokens.json, PAT switch). The v0.7.0 skill scored below the no-skill baseline because it steered the agent back to re-running 'nxd login'. The no_skills row (from the after-report batch) is the lift baseline. Scenario is new in the same PR; before-run used a worktree of main with the scenario copied in.

Record: [`records/2026-07-06-nxd-setup-sandboxed-shell-headless-device-flow-branch.json`](records/2026-07-06-nxd-setup-sandboxed-shell-headless-device-flow-branch.json)
