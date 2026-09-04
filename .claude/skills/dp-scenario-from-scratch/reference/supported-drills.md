# Which drills the harness can already grade

## Contents

- [Why this list is the gate](#why-this-list-is-the-gate)
- [The supported drills](#the-supported-drills)
- [Matching a contributor's story to a drill](#matching-a-contributors-story-to-a-drill)
- [What escalation looks like](#what-escalation-looks-like)

## Why this list is the gate

A scenario's specific check is a `FollowUpKind` — Python that reads the run's
artifacts and decides pass or fail. If a contributor's story needs a check that
is not in this list, it needs new code, and new code needs mutation testing by
an engineer before anyone should believe its verdict.

So this list is the escalation boundary. Matching one of these means the
scenario is declarative and a contributor can finish it. Not matching means
stop.

## The supported drills

| Kind | The failure it catches |
|---|---|
| `capability_shortfall` | The source genuinely cannot answer part of the question. The agent must refuse the impossible parts, label the proxies, and record those limits as governed decisions rather than invent numbers. |
| `grain_and_aggregation` | A join fans a parent value out across children, so totals inflate. Reconciliation is against a control total, because self-consistent wrong numbers agree with each other. |
| `optional_required_outputs` | A valid source that yields no rows. Manufacturing a placeholder row fails; so does relaxing the checks that guard genuinely required outputs. |
| `credential_rotation` | Credentials change mid-run. Graded on connection-level evidence rather than the agent's account of what happened. |
| `sigterm_diagnosis` | A step is killed for resource reasons. The graded difficulty is the *diagnosis* — attributing it correctly rather than to memory, a timeout, or a code bug. |
| `restart_and_switch` | Serving is down versus the build is broken. The agent must tell them apart and change the plan rather than retry until lucky. |

## Matching a contributor's story to a drill

Listen for the shape, not the vocabulary. Some real mappings:

- *"They keep asking how long deals have been sitting in a stage, but all we
  store is a last-updated timestamp"* → `capability_shortfall`.
- *"The revenue total was three times too big once we broke it out by line
  item"* → `grain_and_aggregation`.
- *"The report was empty and someone filled in a zero row so it wouldn't look
  broken"* → `optional_required_outputs`.

If two drills seem to fit, prefer the one whose *wrong answer* matches theirs
most exactly. The wrong answer is what the scenario grades.

## What escalation looks like

Tell the contributor plainly, in their words, without the harness vocabulary:

> What you're describing needs a new kind of check that doesn't exist yet — the
> harness can't currently tell a right answer from a wrong one for this
> situation. I've written down what you told me so an engineer can pick it up.
> That's a genuinely useful finding, not a dead end: it means we're missing a
> whole category of test.

Then write what they said into
`evals/dp-scenarios/scenarios/_proposed/<id>.md`: their opening words, the data
and what it lacks, the plausible wrong answer, the right answer, and how they
behave mid-stream. An engineer needs exactly those five things to build the
check, and they are the part only the contributor could supply.

Do not write the Python. A check written without mutation testing is the failure
this whole process exists to prevent.
