---
id: 2026-09-07-background-subagents-void-the-run
date: 2026-09-07
label: "run subagents inline, deny the session tools, and fail a run that built nothing"
plugin_version: 0.45.1
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — run subagents inline, deny the session tools, and fail a run that built nothing

## Notes

Harness runtime policy and grading. No skill under `src/` changes in this entry;
the tool policy is agent-capability-visible.

**What happened.** A live `crm-pipeline` run ended `ungraded` at 217s (normal is
~900s) with score 0 and every gate unexamined. The agent dispatched one
subagent — `Agent{subagent_type: "general-purpose", "Author CRM deals
data-product closure"}` — then spent its remaining eight turns polling with
`ListAgents` and `ScheduleWakeup`, building nothing. Its own words: *"Still
running (no completion notification yet). I have nothing fabricated to report."*

**Root cause, and it is not the session tools.** The CLI runs subagents in the
**background by default**: the launch returns "Async agent launched
successfully" and the child's reply arrives as a task-notification on a *later*
model invocation. This adapter holds one persistent stream-json session whose
per-turn `result` is not held back for a background child, and the scripted
operator advances turns in seconds while a closure-authoring subagent needs
minutes — so the notification never arrives inside the run. Denying the polling
tools alone would have produced eight turns of "still running" with no tool
calls: the same void verdict.

Verified with a matched CLI probe rather than assumed:

| environment | subagent result |
|---|---|
| default | launched in background, no reply |
| `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` | child's reply returned inline in the same tool result |

The adapter now sets that variable for the child. This is the hazard the
`NO_BASH_DELEGATION_TOOLS` comment warned of before it was removed — "leave the
parent turn waiting until its timeout" — but by a different mechanism than the
one it named, which is why removing that denial was still right: step 6b needs
delegation, and the fix is to make delegation synchronous rather than to
withhold it.

**Session tools reached the agent because they were on neither list.**
`--allowedTools` is auto-approval, so omitting a tool grants it. `ListAgents`
and `SendMessage` reach other sessions on this machine, including the grader;
`ScheduleWakeup` and the `Cron*` family inject events no operator turn asked
for, which the turn reader would attribute to the next operator message;
`EnterWorktree` moves the cwd out of the graded workspace; `ExitPlanMode` asks
for an approval headless mode cannot answer. None is used by any skill under
`src/`. They are denied on every run now, not only when Bash is off.

`Monitor` moves into `SHELL_TOOLS`: it executes a shell command, and it still
ran under `--disallowedTools Bash,BashOutput,KillShell`, so the no-shell
guarantee that constant documents was not true. `TaskOutput`/`TaskStop` are
meaningful only for background children and were already denied by alias on
every no-Bash run; naming them makes the allow-Bash path agree.

**Two grading defects the same run exposed.**

*A run that produced nothing was voided rather than failed.* `scenario.py`
coerced a follow-up `not-examined` into `ungraded`, and an `ungraded` result
voids a run. So an agent that stalls and writes no evidence artifact escapes a
loss — the "dodge a gate by producing nothing" hole the requiredness work exists
to close, surviving in the follow-up path. `gates.py` already states the correct
policy: `ungraded` is for a planted check that fired and measured nothing. Only
an explicit `ungraded` voids now.

*A background launch counted as a dispatch.* `_construction_call_kinds` marked
`_delegated` on any non-error `Agent` result, and "Async agent launched
successfully" is non-error with no child reply — so a detached launch plus a
hand-written `review_rounds[]` entry would have satisfied the reviewer half with
no review having happened.

**Deliberately not done.** No prompt or conduct rule discourages delegating the
authoring work. `nxd-run-job-loop` explicitly permits offloading its steps 2–3
to subagents, so a rule against it would countermand a skill under test — the
thing `test_no_conduct_rule_countermands_the_skills_under_test` exists to
prevent. What that run actually did wrong (telling the subagent not to run the
self-check, accepting prose instead of the structured hand-back) is already
gradable and already fails `construction`. One mechanics sentence was added to
the prompt stating that background execution is off, because the CLI's own
prompt asserts the opposite affordance.

## Evidence

- `evals/dp-scenarios/tests/test_runner_claude_adapter.py` — `Monitor` is in the
  shell surface, the session tools are denied on every run, `Task`/`Agent` stay
  available, and `TaskOutput`/`TaskStop` are denied. Fails against the previous
  implementation.
- `evals/dp-scenarios/tests/test_grading_gates.py` — an "Async agent launched"
  result is not credited as a dispatch. Fails against the previous
  implementation.
- `evals/dp-scenarios/tests/test_scenario_crm_pipeline.py` — a fired plant with
  no evidence artifact is a failure with `crm_pipeline_not_examined`, not a void
  run. Fails against the previous implementation.
