---
name: dp-scenario-from-scratch
description: Interview someone about a data request that went wrong, and turn their answers into a runnable dp-scenarios test. Use when a colleague wants to contribute an eval scenario from their own domain — a report that came back subtly wrong, a question the data could not really answer, a stakeholder who changed their mind mid-build. Handles all the harness mechanics; asks only about the business situation.
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

# Turn a real data problem into a test

You are interviewing someone who knows a business domain, not this harness. They
may be in finance, marketing, sales ops, or anywhere else. **Assume they have
never heard of a gate, a fixture, a plant, or a turn budget, and never use those
words with them.** You do the mechanics; they supply the thing only they have.

## What you are trying to get from them

The scarce input is a story about work that went wrong in an interesting way.
Specifically five things:

1. **How they would have asked.** Their actual opening words — vague, the way a
   real request is. "How is our pipeline moving?" not "build me a stage-age
   table grouped by owner."
2. **What the data really is.** Where it lives, what it contains, and — this is
   the important part — **what it does not contain**.
3. **The plausible wrong answer.** What a competent-but-hasty analyst would
   hand back, and why it is wrong. This is the heart of the test. A scenario
   without a specific wrong answer grades nothing.
4. **The right answer**, or the right *refusal*. Sometimes the correct outcome
   is "you cannot answer that from this source, and here is why."
5. **How they behave mid-stream.** Do they approve without reading? Change the
   definition halfway? Push back on a correct answer? Go quiet?

## How to run the interview

Ask about **one** of these at a time and let them talk. Do not present a form.

Good openers:

- "Tell me about a report or dashboard that came back looking fine but was
  actually wrong. What was wrong with it?"
- "Is there something people keep asking for that your data can't really
  answer? What do they ask, and what do you have instead?"
- "When you ask for something like this, what do you usually say first?"

When they describe the wrong answer, dig until you have something checkable:

- "How would you *know* it was wrong? What would you compare it against?"
- "Was the number too big, too small, or just measuring the wrong thing?"
- "If someone handed you both answers, what would tell them apart?"

That last one matters most. If nothing distinguishes right from wrong except
judgement, say so plainly and stop — see **When to stop** below.

Also ask, because it decides whether the scenario is buildable:

- "Roughly how many rows, and does the exact number matter?"
- "Is any of this sensitive — something that must never appear in output?"

## What you build from their answers

Everything goes in `evals/dp-scenarios/scenarios/<id>/`. Read
`reference/scenario-anatomy.md` for the file-by-file shape and
`reference/interview-to-artifacts.md` for how each answer maps onto it.

In short: their opening words become the first operator turn; their facts become
the answer sheet the operator replies from; their mid-stream behaviour becomes
either a persona or an injected event; the right answer becomes the gold the
run is graded against.

Mark the scenario a draft. Add `tier: draft` in `scenario.yaml` and say in the
scenario's `README.md` that it has not been mutation-tested yet.

## When to stop and hand off

**Stop and escalate to an engineer** rather than inventing anything, when:

- **The drill needs a check that does not exist.** The supported drills are
  listed in `reference/supported-drills.md`. If what they describe is not one of
  them, it needs new grading code — say so and stop. Do not write Python.
- **Right and wrong cannot be told apart mechanically.** If distinguishing them
  needs a human to read the output and judge, this harness cannot grade it. That
  is a real finding; write it down and tell them why.
- **The data cannot be synthesised.** Fixtures are generated from a seed, never
  copied from production. If the situation only reproduces on real customer
  data, stop.

Say plainly which of these you hit, and what an engineer would need to add.
Do not produce a scenario that looks complete and grades nothing — that is worse
than producing none, because it will be trusted.

## Before you hand it back

Run these and show the output:

```bash
uv run --project evals/dp-scenarios python -m pytest evals/dp-scenarios/tests -q
```

Then tell the contributor, in their words, three things: what the scenario now
tests, what it does **not** test, and that an engineer must mutation-test the
checks before it can be trusted — that step is what catches a check that
silently grades nothing, and it is not optional.
