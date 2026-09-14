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
   is "you cannot answer that from this source, and here is why." Ask which
   one it is, plainly: *"if they came back and asked you for that number, would
   you have it somewhere else, or does it simply not exist?"* Their answer sets
   `gap_stance` — see `reference/interview-to-artifacts.md`. It is the
   difference between an operator who sends the agent looking and one who tells
   it to stop looking, and getting it backwards wastes the whole run.
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

Everything goes in **`evals/dp-scenarios/scenarios/_proposed/<id>/`** — not
directly under `scenarios/`. Read `reference/scenario-anatomy.md` for the
file-by-file shape and `reference/interview-to-artifacts.md` for how each
answer maps onto it.

`_proposed/` is where contributed packages wait. The loader reads only the
top level of `scenarios/`, so a package parked one level down is invisible to
it — which is what you want, because an incomplete package placed directly
under `scenarios/` does not merely fail to run: it makes the whole scenario
root unloadable and every test that reads it goes red at once. An engineer
moves the directory up when it is ready.

In short: their opening words become the first operator turn; their facts become
the answer sheet the operator replies from; their mid-stream behaviour becomes
either a persona or an injected event; the right answer becomes the gold the
run is graded against.

Declare a real tier — `smoke`, `core`, `full`, or `live`; there is no `draft` tier and
the loader rejects one. Being under `_proposed/` is what marks it unfinished.
Say in the scenario's `README.md` that it has not been mutation-tested yet.

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

**Check the package itself.** Nothing under `_proposed/` is read by the test
suite — that is the point of parking it there, but it means a green suite says
nothing about your package. Load it directly:

```bash
uv run --project evals/dp-scenarios python -c "
from dp_scenarios.scenario import load_scenario
from dp_scenarios.grading.gates import GATE_PHASES
s = load_scenario('evals/dp-scenarios/scenarios/_proposed/<id>')
assert s.seed == 29, f'seed must be 29, got {s.seed}'
assert s.coverage['variant'] == s.fixture_variant, 'coverage.variant must equal fixture.variant'
assert s.coverage['untested'], 'coverage.untested must not be empty'
assert set(s.gates) == set(GATE_PHASES), f'gates must be all seven, missing {set(GATE_PHASES) - set(s.gates)}'
assert s.turn_budget == len(s.answer_sheet.turns), f'turn_budget {s.turn_budget} != {len(s.answer_sheet.turns)} turns'
assert s.required_plants, 'required_plants must not be empty'
print('package is sound:', s.id, '| tier:', s.tier, '| turns:', len(s.answer_sheet.turns))"
```

Each failure names the exact key. Fix until it prints `package is sound`.
**Do not skip this** — without it a missing key or a wrong persona path stays
invisible until an engineer promotes the directory, and surfaces to them
rather than to you.

The asserts are not decoration. The three they add are guarded in three
different ways, and only one of them is guarded anywhere else:

- **`seed: 7`** loads fine. It is checked only by a test that skips
  `_proposed/`, so without the assert it waits until promotion to fail.
- **`turn_budget` larger than the script** is enforced by **nothing, ever** —
  the loader checks only a floor, and the equality test is hardcoded to
  `capability-shortfall`. Without the assert it never fails at all; it quietly
  misreports the efficiency ratio for the life of the scenario.
- **`coverage.variant` not matching `fixture.variant`** is caught by the loader
  itself, so that assert is belt-and-braces rather than the only guard.

Then run the suite, which checks you have not broken anything else:

```bash
uv run --project evals/dp-scenarios python -m pytest evals/dp-scenarios/tests -q
```

Then tell the contributor, in their words, three things: what the scenario now
tests, what it does **not** test, and that an engineer must mutation-test the
checks before it can be trusted — that step is what catches a check that
silently grades nothing, and it is not optional.
