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

Put the package in **`evals/dp-scenarios/scenarios/_proposed/<id>/`**, not
directly under `scenarios/`: the loader reads only the top level, so a package
one level down is invisible to it, while an incomplete one placed directly
under `scenarios/` makes the whole scenario root unloadable. Declare a real
tier (`smoke`, `core` or `live`) — there is no `draft` tier — and say in the
scenario `README.md` that it has not been mutation-tested.

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

The asserts are not decoration, and the three they add are each unenforced in
a different way:

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

Then tell them, in their own terms: what the scenario now catches, what it does
not, and that an engineer must mutation-test the checks — deliberately break
each one and confirm a test fails — before its verdict can be trusted.
