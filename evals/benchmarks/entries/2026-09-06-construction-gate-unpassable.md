---
id: 2026-09-06-construction-gate-unpassable
date: 2026-09-06
label: "stop the harness preventing, mislabelling and diverting the behaviour construction grades"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — stop the harness preventing, mislabelling and diverting the behaviour construction grades

## Notes

Harness grading, tool policy and prompt mechanics. No skill under `src/`
changes, so no runnable public arm can distinguish any of it; the tool-policy
and prompt parts are agent-visible.

`construction` had never passed on a live run. Four separate defects were
responsible, all of the same shape: **the harness graded a behaviour it had
itself prevented, mislabelled, or diverted the agent away from.** They are one
entry because they are one bug — found in four stages only because each fix
uncovered the next.

### 1. The gate asked for testimony about an event it had witnessed

`gate_construction` required, per kind, an outcome *and* an attestation *and* an
observed call. But `_construction_call_kinds` already records `self_check` from
a non-error `mcp__nxd-desktop__check_data_product` at the structured session
boundary — harness-owned evidence of the same event the attestation would
describe. A live run that called it successfully before every build still failed
on `self_check_outcome_missing` and `self_check_attestation_missing`: the
harness failing an agent for not re-telling it what it had just seen. This is
the pattern already removed from the build gate, where examinability depended on
which artifacts the agent volunteered.

An observed call now satisfies both **for `self_check` only**. The exemption is
deliberately not extended to `adversarial_review`: a delegation call shows that
*a* subagent ran — a documentation-hunting one looks identical at this
boundary — and a `review_rounds[]` entry is agent-written, so neither is the
harness witnessing a review the way a `check_data_product` call is the harness
witnessing a self-check. While the exemption was unscoped, a research subagent
plus a hand-written `{"status": "complete"}` passed `construction` with no
attestation at all, which is a weaker gate than the one this branch started
with.

Not a gate that cannot fail either way: an agent that never calls the tool still
gets `not_observed`.

### 2. The attestation channel had no reachable address

`NXD_EVAL_ATTESTATIONS_PATH` was delivered *only* as an environment variable.
Bash is denied on every run carrying `CLAUDE_CODE_OAUTH_TOKEN` so the token
cannot leak through a shell, and nothing else in the agent's tool set expands a
variable. The agent said so plainly: *"I couldn't write the
self-check/adversarial-review attestations file because this session has no
shell to resolve NXD_EVAL_ATTESTATIONS_PATH."*

The file sits at the agent's own cwd, so it is as nameable as
`infra-profile.yaml` and `scenario-evidence-contract.json`, which the same
prompt already named literally. It is now named — and the next live run wrote a
correct `self_check` attestation there, which is what confirms the diagnosis.
Still required after (1), because the reviewer half has no observable outcome.

`_agent_attestations` also falls back to `artifact_root`. That was removed as
dead — the prompt forbids a live agent to write there — and restored once the
scoping above exposed what it is actually for: a **replay** recording has no
agent workspace, so the artifact root is how it carries the attestations it
recorded. The removal silently emptied every populated replay fixture, and only
the unscoped exemption kept the suite green.

### 3. The delegation tool was denied, then its absence graded

`NO_BASH_DELEGATION_TOOLS = ("Task", "TaskOutput", "Agent")` was appended to
`--disallowedTools` whenever Bash was. But `nxd-generate-data-product` step 6b
*mandates* dispatching `nxd-review-closure` as a read-only subagent, and the
gate accepts only that dispatch or an inline `Skill` call. The inline route is
not a substitute: the same context would review the closure it just authored,
which is the one property the reviewer exists to provide, and it does not
enforce the reviewer's read-only tool set.

Restoring delegation is safe, and this was verified against the CLI rather than
assumed — `--disallowedTools` **is** inherited by subagents:

| argv | subagent result |
|---|---|
| `--allowedTools Task` + `--disallowedTools Bash,BashOutput,KillShell` | denied |
| `--allowedTools Task,Bash` (control) | executed |

The matched control is what makes that evidence rather than a model declining.
`SHELL_TOOLS` stays denied, so the shell — and the OAuth token in the process
environment — remains unreachable directly and through delegation. The deny
list's original rationale (delegated steps stalling on shell-only validators) is
a prompt concern and the prompt already carries it.

### 4. The gate watched for a tool name the CLI does not use

With delegation restored, the next live run made **four `Agent` calls and zero
`Task` calls**. The gate matched only `name == "task"`, so the dispatch was
unobservable *by name*: an agent doing exactly what step 6b mandates would still
have been graded `adversarial_review_not_observed`. Both names are accepted now,
and `--allowedTools` gained `Agent` for the same reason — that list is
auto-approval, and naming one spelling was an accident of which build it was
written against.

### 5. The prompt told the agent to skip the skill containing that step

The same run never invoked `nxd-generate-data-product` at all — zero references
in the transcript. It routed through `nxd-run-job-loop`, which is the correct
entry point (its description says a direct build request starts there), but the
loop is a superset that *invokes* the generator, and that handoff never
happened. The agent explained itself in a subagent prompt: *"without using the
nxd-generate-data-product skill's automated flow (I'm told to author
directly)."*

What told it was the harness: "do not launch a background Agent for shell-only
validation or helper-script discovery; **author the closure with the available
file tools** and use the nxd-desktop check/build/query MCP tools for runtime
verification." Two diversions in one sentence — the first bans the dispatch the
mandated step needs, the second reads as "author directly" rather than "write
files without a shell".

The narrow intent remains: shell-only helpers cannot run, so substitute file
tools and MCP verification. The replacement says that and adds that it
substitutes *a mechanism, not a workflow*, directing the agent to follow the
skills' normal flow including any step that dispatches a subagent. It names no
gate and no observed skill, so it stays harness mechanics rather than a hint —
the property `test_the_default_prompt_does_not_restate_what_the_gates_grade`
protects.

### 6. The gate's success token could not be emitted at all

The deepest defect, and the one that made every fix above insufficient.
`_construction_call_kinds` credited `adversarial_review` only for a delegation
call whose `subagent_type` was `nxd-review-closure`. But
`reference/adversarial-review.md` mandates "one built-in read-only subagent —
**never** add, select, or rely on a custom/plugin agent definition";
`.claude-plugin/plugin.json` registers no agents, only skills; `stage_plugin`
copies `src/` alone; and the CLI rejects an unknown subagent type outright. The
value the gate required is one a *compliant* agent can never produce, and the
only alternative the gate accepted — an inline `Skill` call — is the one the
adapter's own comment calls not adversarial, because the same context would
review its own closure.

So the gate demanded either an impossible token or a disqualified substitute.
The same defect class as a gate reading a spec the product never writes.

What the mandated flow *does* produce is a `review_rounds[]` entry in
`build-record.json`: the dispatcher records every returned claim, or a terminal
`timed_out` round, and adjudicates it with a citation. The gate now reads that,
paired with an observed delegation call. Both halves are required, and the
pairing is what keeps it honest — a research subagent records no round, and a
fabricated round dispatched nothing. Run 3's four `Agent` calls (documentation
hunting and a file deletion) are correctly credited with no review.

The round also carries the outcome, so `adversarial_review` becomes
harness-owned rather than agent-attested — the same move made for the
self-check in (1). `skipped` is not accepted: the contract is explicit that a
non-eligible review produces no entry, so an entry claiming `skipped` is not a
round.

### 7. A conduct rule instructed the graded failure

The system-prompt diversion in (5) had a twin. Conduct rule 7, delivered in
`scenario-evidence-contract.json` and read by the agent in its first turn, said:
"After the operator approves the blueprint, do not ask for another
confirmation, **load a planning skill, or delegate a helper**; author the
closure and call check_data_product directly." That is an instruction to
hand-author and not to delegate — precisely the two behaviours `construction`
failed the run for missing. While it stood, the reworded system prompt and the
contract contradicted each other in the same context.

The rule's anti-stall purpose survives; the clauses that countermanded the
skills under test are gone. A conduct rule may constrain how the agent treats
the *operator*; it must not overrule the skills being measured.

### What this does and does not establish

Across three live `crm-pipeline` runs the `construction` findings fell from five
to three, the self-check half clearing once (2) landed. Note that run 3 predates
(4) and (5) — both landed after it started — so the tool-name fix, the prompt
reword, and (6) and (7) have never been exercised live. **It does not establish
that `construction` will now pass.** Whether an agent follows the flow through
step 6b and dispatches the reviewer is agent behaviour; the harness no longer
prevents it, mislabels it, or diverts the agent away from it, which is the limit
of what a harness change can settle. Runs taken before the tool-policy change
are not comparable with later ones on this gate.

## Evidence

- `evals/dp-scenarios/tests/test_grading_gates.py` — an observed
  `check_data_product` with no ledger row and no attestation passes while the
  reviewer half still requires an attestation; a run that never calls the tool
  still fails with all three self-check findings; and a reviewer dispatch is
  observed under both `Task` and `Agent`. The first and the `Agent` case both
  fail against the previous implementation.
- `evals/dp-scenarios/tests/test_runner_claude_adapter.py` — a Bash-denied argv
  denies the three shell tools and denies none of `Task`/`TaskOutput`/`Agent`.
  Both assertions fail against the previous implementation. Note the safety
  argument now rests on `--disallowedTools` being inherited by subagents, which
  these assertions do not pin: they inspect argv composition only, so a CLI
  change that stopped propagating the deny list would not be caught here.
- `evals/dp-scenarios/tests/test_runner_environment.py` — the diverting
  sentences are gone, the mechanism-not-workflow wording is present, and the
  guidance names neither the observed skill nor the dispatch shape the gate
  looks for. Fails against the previous prompt.
- `evals/dp-scenarios/tests/test_runner_tier.py` — `_agent_attestations` reads
  the agent workspace only.
- `evals/dp-scenarios/tests/test_grading_gates.py` — a delegation call paired
  with a recorded `review_rounds[]` entry passes; neither half alone counts,
  and a `skipped` status is not a round.
- `evals/dp-scenarios/tests/test_runner_environment.py` — no conduct rule names
  a planning skill, a delegated helper, or authoring the closure directly,
  while the anti-stall clause survives.
