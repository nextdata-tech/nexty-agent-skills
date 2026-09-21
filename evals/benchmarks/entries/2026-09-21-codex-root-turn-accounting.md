---
id: 2026-09-21-codex-root-turn-accounting
date: 2026-09-21
label: "fix Codex root-turn terminal accounting"
plugin_version: 0.51.6
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — fix Codex root-turn terminal accounting

## Notes

Harness-only. No shipped skill or scenario declaration changed, so no existing
public scenario can distinguish this change. The fix corrects provider-event
accounting and qualification diagnostics in the alternate Codex live runner.

The Codex app server can emit a child review turn completion alongside the
owning operator turn completion. The adapter now preserves the root turn ID
and counts only terminal events for that root. The qualification path also
reports `script_exhausted` distinctly from the `turn_timeout_truncated` reason;
both remain incomplete evidence and neither is a pass.

The carrying B3 Codex run had eight successful operator turns, but turn 3 was
recorded with two terminal results after a reviewer child completed. That made
the engine classify the otherwise observed session as `script_exhausted`, and
the tier then correctly voided it as incomplete evidence. No scenario pass is
claimed. The live run also had genuine construction blockers and did not reach
publication or query.

The corrected runner was then exercised against the same B3 scenario and real
supervisor. All eight turns recorded exactly one root terminal result, the
engine ended `completed`, and the scenario was reported as a scored `failed`
run with the same genuine construction blockers. This validates the runner's
classification change, not the skill's scenario quality, so it remains
NO_EVAL evidence.

## Evidence

The carrying tests are
`evals/dp-scenarios/tests/test_runner_codex_adapter.py`,
`evals/dp-scenarios/tests/test_runner_qualification_reasons.py`, and
`evals/dp-scenarios/tests/test_runner_tier.py`.
