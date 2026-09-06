---
id: 2026-09-06-restore-reviewer-delegation
date: 2026-09-06
label: "stop withholding the subagent the skill mandates and the gate grades"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — stop withholding the subagent the skill mandates and the gate grades

## Notes

Harness runtime policy only; no skill under `src/` changes, so no runnable
public arm can distinguish it. It is agent-capability-visible: the agent under
test regains a tool.

**The contradiction.** `NO_BASH_DELEGATION_TOOLS = ("Task", "TaskOutput",
"Agent")` was appended to `--disallowedTools` whenever Bash was denied, and Bash
is forced off on every run carrying `CLAUDE_CODE_OAUTH_TOKEN` so the token
cannot leak through a shell. But `nxd-generate-data-product` step 6b *mandates*
dispatching `nxd-review-closure` as a read-only subagent, and
`_construction_call_kinds` accepts exactly two observations for
`adversarial_review`: a `Task` with that `subagent_type`, or an inline `Skill`
call. With `Task` denied, the harness withheld the mechanism the skill requires
and then graded its absence as an agent failure — `construction` was unpassable
on every OAuth live run for a reason the agent did not control.

The remaining inline `Skill` route is not a substitute. It is not adversarial:
the same context would review the closure it just authored, which is the one
property `nxd-review-closure` exists to provide, and it does not enforce the
reviewer's read-only tool set.

**Why restoring it is safe.** The concern was the credential: the OAuth token
lives in the agent process's environment, and a subagent with a shell could read
it. Verified against the CLI that this cannot happen — `--disallowedTools` is
inherited by `Task` subagents:

| argv | subagent result |
|---|---|
| `--allowedTools Task` + `--disallowedTools Bash,BashOutput,KillShell` | denied |
| `--allowedTools Task,Bash` (control) | executed |

The matched control is what makes this evidence rather than a model declining:
the same prompt and the same subagent dispatch succeed when `Bash` is permitted.
`SHELL_TOOLS` stays denied, so the shell — and the token behind it — remains
unreachable, directly and through delegation.

**The original reasoning is addressed where it belongs.** The deny list's
comment said delegated skill steps "cannot access the shell-only validators and
otherwise leave the parent turn waiting until its timeout". That is a prompt
concern, and the prompt already carries it: "When Bash is unavailable, do not
launch a background Agent for shell-only validation or helper-script
discovery." Denying the tool outright was a blunt instrument for a narrow
hazard, and it cost a mandated skill step.

**Comparability.** The system prompt and tool policy are not part of run
identity — the manifest hashes only the judge and persona prompts — so no
recorded run changes. The two live `crm-pipeline` runs from today were both
taken under the old policy and should not be compared with any later run on
`construction`.

## Evidence

- `evals/dp-scenarios/tests/test_runner_claude_adapter.py` — a Bash-denied argv
  denies the three shell tools and denies none of `Task`/`TaskOutput`/`Agent`;
  an OAuth run forces the shell off while leaving delegation available. Both
  assertions fail against the previous implementation.
