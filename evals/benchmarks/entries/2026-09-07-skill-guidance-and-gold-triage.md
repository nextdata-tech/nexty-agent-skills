---
id: 2026-09-07-skill-guidance-and-gold-triage
date: 2026-09-07
label: "clarify generator review guidance and preserve gold-failure triage"
plugin_version: 0.45.1
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — clarify generator review guidance and preserve gold-failure triage

## Notes

This is a single, scoped NO_EVAL entry for the shipped-skill and deterministic
follow-up fixes in PR #240. It is not a duplicate of
`2026-09-07-background-subagents-void-the-run`, which covers only the Claude
adapter's session policy and run qualification; that entry deliberately has no
`src/` skill changes.

No controlled before/after scenario arm was run against this exact final skill
surface. The available live B-series runs are repeated diagnostic runs with
unqualified outcomes, not paired benchmark arms that isolate these prose and
gold-triage changes. Manufacturing a PASS/FAIL pair from them would make the
benchmark record less trustworthy. The carrying tests below exercise the
changed contracts directly.

## Evidence

- `evals/dp-scenarios/tests/test_followup_gold_status.py` — malformed committed
  gold is ungraded while findings measured before the gold read remain visible.
- `evals/dp-scenarios/tests/test_scenario_restart_and_switch.py` — invalid oracle
  gold does not emit the unreachable `attempts_not_reconciled_against_oracle`
  finding.
- `evals/dp-scenarios/tests/test_runner_claude_adapter.py` — the spawned
  delegation/session-tool policy remains explicit and testable.
- `evals/dp-scenarios/tests/test_runner_environment.py` — the default prompt
  continues to describe mechanics without countermanding the skill flow.
