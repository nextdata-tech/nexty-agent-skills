---
name: dp-scenario-from-session
description: Turn a real session where a data product was built into a runnable dp-scenarios test. Use when someone points at work that already happened — a build that went wrong, a definition that changed halfway, a number nobody caught — and wants it captured as a regression test. Reads the session's own artifacts and asks the person only what the artifacts cannot tell you.
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

# Turn a session that already happened into a test

Someone has a real build — a closure, a transcript, a job directory — and wants
the situation captured so it cannot silently recur. Most of what you need is in
those artifacts. **Read first, ask second**, and ask only about the things the
artifacts genuinely cannot tell you.

Assume the person knows their data and not this harness. Never use the words
gate, fixture, plant, or turn budget with them.

## Read the session first

Ask where the work is, then read it. See
`reference/reading-a-session.md` for where each thing lives and what it tells
you.

From the artifacts you can usually recover, without asking:

- what was asked for, and how the definition changed over the session
- what was built: models, columns, transforms
- what judgement calls were made and whether they were recorded
- what the source could and could not supply
- where the numbers came from

## Then ask only what is missing

Artifacts record what happened. They do not record **what should have
happened**, and that is the whole test. Ask:

1. **"What actually went wrong here?"** — or if nothing did, "what nearly went
   wrong, or what would have if someone had been less careful?"
2. **"How would someone have caught it?"** What would you compare against?
3. **"What would the sloppy version of this have looked like?"** This becomes
   the failure the test detects.
4. **"How much of what you told them mid-way should they have worked out
   alone?"** This decides which facts are handed over and which are withheld.

Question 4 is the one people find surprising and it is the most important. A
session transcript shows a human volunteering context. A good scenario withholds
most of it, because the point is whether the agent asks.

## Build the scenario

Files and shapes are in
`.claude/skills/dp-scenario-from-scratch/reference/scenario-anatomy.md` — the
package is identical however it was sourced. What differs is where the content
comes from: `reference/reading-a-session.md` maps each artifact onto the file it
becomes.

Two rules specific to this path:

- **Regenerate the data; never copy it.** Fixtures come from the seeded
  generator. Real rows must not enter the repo, and a scenario that only
  reproduces on production data cannot run in CI. Take the *shape* and the
  defect, not the rows.
- **Strip anything identifying.** Customer names, emails, internal URLs,
  credentials. If the drill genuinely needs a sensitive value present, it must
  be a planted marker the harness generates, not a real one.

Mark it a draft: `tier: draft`, and say in the scenario `README.md` that it has
not been mutation-tested.

## When to stop and hand off

Same boundary as authoring from scratch, and
`.claude/skills/dp-scenario-from-scratch/reference/supported-drills.md` is the
list. Stop and escalate when:

- **The drill is not in that list** — it needs new grading code. Write down what
  you learned and hand it to an engineer. Do not write Python.
- **Right and wrong cannot be told apart mechanically.** If catching the failure
  needed a human to read the output and use judgement, this harness cannot grade
  it. Say so; it is a real finding.
- **The failure depends on real data.** If it will not reproduce from a seeded
  fixture, it cannot become a scenario here.

One trap specific to this path: a session that went *well* is not automatically
a scenario. If the agent did everything right and nothing was at stake, there is
no failure to detect — and a scenario that cannot fail is worse than none,
because it will be trusted. Ask what the sloppy version would have looked like;
if there isn't one, say so and stop.

## Before you hand it back

```bash
uv run --project evals/dp-scenarios python -m pytest evals/dp-scenarios/tests -q
```

Then tell them, in their own terms: what the scenario now catches, what it does
not, and that an engineer must mutation-test the checks — deliberately break
each one and confirm a test fails — before its verdict can be trusted.
