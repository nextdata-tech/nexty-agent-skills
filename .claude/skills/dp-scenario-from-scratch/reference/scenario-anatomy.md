# What a scenario package contains

## Contents

- [The five files](#the-five-files)
- [scenario.yaml](#scenarioyaml)
- [answer-sheet.yaml](#answer-sheetyaml)
- [events.yaml](#eventsyaml)
- [gold/](#gold)
- [README.md](#readmemd)
- [Choosing a persona](#choosing-a-persona)
- [Rules that are easy to get wrong](#rules-that-are-easy-to-get-wrong)

## The five files

A contributed package lives in `evals/dp-scenarios/scenarios/_proposed/<id>/`
until an engineer promotes it to `scenarios/<id>/`. The loader reads only the
top level of `scenarios/`, so a package one level down is invisible to it —
and an incomplete package placed directly at the top level makes the *entire*
scenario root unloadable, failing every test that reads it.

While parked in `_proposed/` a package is fully additive — it touches no shared
file, so two people can author at once without conflicting. **That stops being
true at promotion**: `test_scenario_loader.py` keeps a hand-maintained tier map
whose key set must equal the packages on disk, so an engineer adds a line there
when they move the directory up. Deliberate, so a new scenario cannot appear
unnoticed.

```
scenarios/_proposed/<id>/      # promoted to scenarios/<id>/ when ready
  scenario.yaml       what to run, how to grade it
  answer-sheet.yaml   what the operator says and knows
  events.yaml         things injected mid-conversation
  gold/               the truth the run is graded against
  README.md           what this drills, and what it does not
```

## scenario.yaml

**Sixteen keys are required.** The loader raises `scenario is missing key(s): …`
if any is absent, so this is the whole set, not a selection:

`version` `id` `tier` `run_order` `fixture` `coverage` `turn_budget`
`repeatability` `persona` `answer_sheet` `events` `phase_map` `required_plants`
`gates` `gold` `operator`

What each must contain:

| Field | Requirement |
|---|---|
| `version` | Integer `1`. |
| `id` | Must equal the directory name. |
| `tier` | One of `smoke`, `core`, `full`, `live`, `T0`. **There is no `draft` tier.** Being under `_proposed/` is what marks a package unfinished. |
| `run_order` | Unique **across the whole root**, not within your tier. Every value 1-6 is already taken, so start at 7 and check first: `grep -h '^run_order:' evals/dp-scenarios/scenarios/*/scenario.yaml`. |
| `fixture.dataset` | `grain_trap` or `zero_row_optional`. |
| `fixture.seed` | **Must be `29`.** Asserted for every package, so generated data is comparable. |
| `fixture.variant` | Required. A name for this scenario's shape of the dataset. |
| `fixture.plant` | Set in five of the six shipped packages, and **mandatory when `dataset` is `zero_row_optional`** — omitting it there raises `fixture requires dataset, seed, variant, and plant`. For `grain_trap` it may be omitted, and one package does. |
| `coverage.variant` | Must equal `fixture.variant` exactly. |
| `coverage.untested` | Non-empty prose saying what this scenario does *not* establish. |
| `turn_budget` | The loader only requires it to be **at least** the turn count. Set it **equal** anyway: the efficiency ratio and the budget-exceeded check both read it as the exact script length, so a larger value quietly misreports both. Only `capability-shortfall` has a test pinning the equality. |
| `phase_map` | Every turn number to a phase, 1-7. |
| `persona` | Resolved **relative to the package directory**, so the depth matters. While parked in `_proposed/` write `../../_personas/<name>.yaml`; when an engineer promotes the directory it becomes `../_personas/<name>.yaml`. Copying the shipped form (`../_personas/…`) into `_proposed/` fails immediately with `persona does not resolve to a file`; forgetting to shorten it at promotion fails then. |
| `answer_sheet` / `events` | Paths to those two files. |
| `repeatability` | The tier and epoch count. Copy a shipped scenario's block. |
| `required_plants` | Non-empty. A scenario with no required plant cannot fail for the reason it was written. |
| `gates` | **All seven keys**: `intake`, `capability`, `narrowing`, `construction`, `build`, `query`, `follow-up`. Not a subset. Leave a value empty for defaults; `follow-up.kind` names the drill. |
| `gold` | Paths to the truth files. |
| `operator` | `sentinel` and `obstacle_terms`. Both may be null/empty, but the key must exist. |

## answer-sheet.yaml

This is the operator's script and everything it knows.

**Ten keys are required** — the loader raises `answer_sheet is missing key(s): …`:

`version` `scenario_id` `opening_message` `turns` `source_answers`
`decision_answers` `status_answers` `opening_forbidden_terms`
`open_decision_markers` `obstacle_terms`

Every key must be present, and emptiness is not uniform:

- `opening_forbidden_terms` and `open_decision_markers` must be **non-empty**.
  `open_decision_markers` is the one nobody guesses — it is the marker text an
  agent uses to flag an unresolved decision, e.g. `[DECISION NEEDED]`.
- `obstacle_terms` is the only list that may be empty.
- `source_answers`, `decision_answers` and `status_answers` may be empty maps.

Two rules that fail at load and surprise people:

- `opening_message` must be **at most one business sentence**.
- `turns[0]` must **equal `opening_message` exactly** — same string, not a
  paraphrase.

`ground_truth`, `driver_forbidden_terms` and `gap_stance` are the **only**
optional keys — and the first two carry most of the scenario's substance.

- `opening_message` — the contributor's own vague first words, verbatim.
- `turns` — a list. A plain string is an ordinary turn. A mapping can declare:
  - `substitute_reply: false` — send this exact line, never a matcher reply.
    **Use this for every question the scenario grades.** An ask that gets
    replaced is an ask that was never made.
  - `approval: true` — transmitting this turn *is* the approval of record.
- `ground_truth` — facts the operator reveals when asked. Each has `terms` (the
  words in an agent's question that trigger it) and `fact` (what it then says).
- `driver_forbidden_terms` — vocabulary the agent must discover for itself.
  Required if the scenario will ever run with a model-driven operator.
- `gap_stance` — what it *means* here when the operator cannot answer
  something. Two values, and the default is usually right:
  - `operator_is_uninformed` (the default) — the data is fine and the gap is
    only this stakeholder's own ignorance. The operator says it does not know
    and tells the agent to look for itself.
  - `source_is_short` — the source genuinely cannot supply what is being
    asked, and saying so is the substance the scenario grades. Use this only
    when the shortfall *is* the drill; otherwise the operator will keep
    insisting the data is not there when it is.

  This is the scenario half of how the operator behaves when it has no answer.
  The other half is the persona's `stance_when_unknown`, which decides the
  voice — the two compose, so a scenario never has to describe a personality
  and a persona never has to know what this particular data can do.

Give the agent room. A live agent needs several turns to author a spec, build,
and self-check. A scenario that asks for results one turn after approval grades
nothing, because there is nothing built yet to grade.

Keep every turn's text distinct, and keep "room" turns neutral — `Please
continue.` and `Go on.` buy time; *"Anything else you want to flag?"* prompts
for the disclosure the drill is supposed to be measuring.

## events.yaml

Things the operator injects mid-conversation. Each card has:

- `trigger_turn` — which turn it rides on.
- `type` — `scope_creep`, `misdiagnosis`, and so on.
- `plant: true` if it is a deliberate trap the run requires to fire.
- `content` — the extra sentence appended to that turn.
- `required_terms` — phrases that must survive into the transmitted message, so
  a rewording operator cannot quietly drop the trap.

## gold/

The truth. Row-sets, control totals, or a capability manifest — whatever the
drill compares against. Generated from the same seed as the fixture so the
numbers are reproducible.

The agent must never be able to read these. That is enforced, not trusted.

## README.md

State the fixture, what the drill is, what it asserts, and — most usefully for
the next reader — **what it does not cover**.

## Choosing a persona

Match the contributor's description of how the stakeholder behaves:

| They said | Persona |
|---|---|
| "They approve whatever you send them" | `rubber-stamper` |
| "They won't commit to a definition" | `anxious-non-decider` |
| "They're sure they're right and they're not" | `confidently-wrong` |
| "They want it yesterday" | `impatient` |
| "They question every column" | `micromanager` |
| "They're relaying for someone else" | `exec-proxy` |

Each persona also declares `stance_when_unknown` — how it hands back a
decision the scenario never encoded (`defer_upward`, `ask_back`,
`push_for_speed`, `approve_anything`, `assert_default`). You do not set it;
it belongs to the persona. It matters to you only because it is why you never
need to write a reply for a question you did not anticipate: the persona
supplies the manner, your `gap_stance` supplies the substance.

## Rules that are easy to get wrong

- **Set `turn_budget` equal to the turn count.** The loader only enforces a floor, so a larger value passes silently and misreports the efficiency ratio.
- **Graded asks need `substitute_reply: false`.** Otherwise the matcher may
  replace the question the scenario exists to ask.
- **The approval turn is never substituted or authored.** Its text becomes the
  approval of record.
- **An event's `trigger_turn` moves when you insert turns above it.** Check it
  after any renumbering.
- **Every gold value comes from the seeded generator**, never from a real
  system.
- **`required_plants` must be non-empty.** A scenario with no required plant
  cannot fail for the reason it was written, and the loader test rejects it.
- **The four that fail loudly and name the whole root, not your package**: `seed: 29`,
  `coverage.variant == fixture.variant`, non-empty `coverage.untested`, and all
  seven gate keys. Getting any of them wrong fails a test that names the whole
  scenario root rather than your package, so check them first when something
  goes red.
