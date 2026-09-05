# Turning what they said into files

## Contents

- [The mapping](#the-mapping)
- [Worked example](#worked-example)
- [You cannot anticipate every question, and you do not have to](#you-cannot-anticipate-every-question-and-you-do-not-have-to)
- [Writing operator turns that do not lead](#writing-operator-turns-that-do-not-lead)
- [Checking your work before handing back](#checking-your-work-before-handing-back)

## The mapping

| What they told you | Where it goes |
|---|---|
| How they would have asked | `answer-sheet.yaml` `opening_message`, and turn 1 |
| What the data contains | `fixture.dataset` + the served source config |
| What the data **lacks** | The gold manifest, and the ground truth explaining the gap |
| The plausible wrong answer | The drill (`gates.follow-up.kind`) and the plant |
| The right answer or refusal | `gold/` |
| How they behave mid-stream | `persona`, and `events.yaml` if it is a specific mid-run change |
| Facts they would give if asked | `ground_truth` entries, with trigger `terms` |
| Words the agent must not be handed | `driver_forbidden_terms` |
| What it means when they *can't* answer | `gap_stance` |

## Worked example

A sales-ops contributor says:

> People keep asking me how long deals have been sitting in their current stage.
> Our CRM export only has a last-updated timestamp — that changes when anyone
> edits anything, not just when the stage moves. Someone built a "days in stage"
> report off that and it was accepted for a quarter before we noticed the
> numbers were nonsense for any deal where the amount had been edited.
> I'd usually just ask "how is our pipeline moving?" and expect them to figure
> the rest out. And honestly, I approve most things without reading them closely.

That yields:

- **Opening**: `How is our pipeline moving?` — verbatim, deliberately vague.
- **The gap**: no stage-entry timestamp; only `updatedAt`. Goes in the gold
  manifest as an impossible metric, and in ground truth as the fact the operator
  will state if asked directly.
- **Wrong answer**: computing days-in-stage from `updatedAt` and presenting it
  as fact, with no caveat. That is `capability_shortfall`.
- **Right answer**: refuse the impossible metrics, or use `updatedAt` as a
  declared *proxy* with the limitation recorded as a governed decision.
- **Persona**: `rubber-stamper`, from "I approve most things without reading."
- **Forbidden terms**: `proxy`, `stage-entry`, and similar — the agent must
  reach the limitation itself, not be handed the word.
- **`gap_stance`**: `source_is_short`. The whole drill is that the CRM export
  cannot answer the question, so when the agent asks, the operator must say so
  flatly rather than "I'm not sure, have a look" — that would send it hunting
  for history that is not there.

Notice what made this work: the contributor supplied a wrong answer that is
**mechanically distinguishable** from the right one. A number presented without
a governed caveat versus one with it — the harness can see that difference.

## You cannot anticipate every question, and you do not have to

A live agent will ask things you never wrote an answer for. That is expected
and it is handled, so do not try to pre-empt it by inventing extra facts — a
fact that is not true of the generated fixture will corrupt the grading, which
is worse than having no answer at all.

What happens instead is a composition of two things you have already chosen:

- The **persona** decides the manner. Each one declares how it hands back a
  question it cannot answer — `exec-proxy` pushes it up the chain,
  `micromanager` asks you what you recommend, `impatient` tells you to take
  the fastest route. You do not write this; picking the persona picks it.
- Your **`gap_stance`** decides the substance, and it is the one you set:
  - `operator_is_uninformed` (the default) — the data is fine, this particular
    person just does not know. The operator says so and tells the agent to look
    for itself.
  - `source_is_short` — the data genuinely cannot answer it, and saying so is
    part of what the scenario grades.

Use `source_is_short` only when the shortfall **is** the drill. Set it
otherwise and the operator will keep insisting the data is missing when it is
not, and the agent will stop looking for something that was there all along.

The one rule this guarantees: however the operator deflects, it always hands
the agent something to act on. An operator that just says "no" and stops is
what wedges a run — the agent waits for a decision that never comes and burns
the rest of the turn budget asking again.

## Writing operator turns that do not lead

The operator is a stakeholder, not a teacher. Turns must not contain the
insight being graded.

| Leading | Neutral |
|---|---|
| "Be careful, `updatedAt` isn't the stage-entry time" | "Can you tell me exactly how long each deal has been sitting in its current stage?" |
| "Anything else you want to flag?" | "Please continue." |
| "Did you check the join grain?" | "The build is ready." |

The second column asks the question and stops. If the agent needs a fact to
proceed, put it in `ground_truth` with trigger terms so the operator supplies it
**when asked**, rather than volunteering it.

## Checking your work before handing back

```bash
uv run --project evals/dp-scenarios python -m pytest evals/dp-scenarios/tests -q
```

Then read the scenario back to the contributor in their own terms:

- What it now tests, in one sentence with no harness vocabulary.
- What it does not test.
- That an engineer still has to mutation-test the checks — break each one
  deliberately and confirm a test fails — before the scenario's verdict means
  anything. Reading a check and agreeing with it has never caught a defect in
  this suite; breaking it has.
