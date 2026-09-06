---
id: 2026-09-06-no-bash-guidance-diverted-the-flow
date: 2026-09-06
label: "stop the no-Bash guidance reading as permission to skip the generator skill"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — stop the no-Bash guidance reading as permission to skip the generator skill

## Notes

Harness prompt mechanics only; no skill under `src/` changes, so no runnable
public arm can distinguish it. It is agent-visible.

**The agent said it in its own words.** In a live `crm-pipeline` run the agent
dispatched a research subagent whose prompt opened: *"I need to author a
Nextdata OS Python data-product closure by hand ... without using the
nxd-generate-data-product skill's automated flow (I'm told to author
directly)."* The transcript contains **zero** references to
`nxd-generate-data-product`; the agent routed through `nxd-run-job-loop` and
hand-authored the closure.

`nxd-run-job-loop` is the correct entry point — its own description says a
direct build request starts there, not in the generator — but the loop is a
superset that *invokes* the generator ("Invoke the **nxd-generate-data-product**
skill: assemble the complete Python-authored ..."). Skipping that step skips
step 6b, which dispatches the closure reviewer, which `construction` then graded
as an agent failure. The agent was not choosing to skip it; it was told to.

**What told it.** The default system prompt's no-Bash paragraph read: "do not
launch a background Agent for shell-only validation or helper-script discovery;
**author the closure with the available file tools** and use the nxd-desktop
check/build/query MCP tools for runtime verification." Two separate diversions
in one sentence — the first bans the dispatch the mandated step needs, the
second reads as "author directly" rather than "write files without a shell".

The intent was narrow and remains: shell-only helper scripts cannot run, so
substitute file tools and MCP verification. The replacement says exactly that
and adds that it substitutes *a mechanism, not a workflow*, directing the agent
to follow the skills' normal flow including any step that dispatches a
subagent. It names no gate and no skill whose dispatch is observed, so it stays
harness mechanics rather than a gate hint — the property
`test_the_default_prompt_does_not_restate_what_the_gates_grade` protects.

**This is the fourth defect in one family** — [[2026-09-06-construction-observed-self-check]],
[[2026-09-06-restore-reviewer-delegation]], [[2026-09-06-reviewer-dispatch-tool-name]] and this
one — all the harness preventing, mislabelling, or diverting the very behaviour
it graded. Together they are why `construction` had never passed on a live run.
None of them establishes that it now will: whether an agent follows the flow
through step 6b is agent behaviour, and it remains unmeasured.

## Evidence

- `evals/dp-scenarios/tests/test_runner_environment.py` — the diverting
  sentences are gone, the mechanism-not-workflow wording is present, and the
  guidance still names no observed skill. Fails against the previous prompt.
