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

Everything lives in `evals/dp-scenarios/scenarios/<id>/`. A package is additive:
it needs no edit to any shared file, so two people can author scenarios at the
same time without conflicting.

```
scenarios/<id>/
  scenario.yaml       what to run, how to grade it
  answer-sheet.yaml   what the operator says and knows
  events.yaml         things injected mid-conversation
  gold/               the truth the run is graded against
  README.md           what this drills, and what it does not
```

## scenario.yaml

The load-bearing fields:

| Field | What it does |
|---|---|
| `id` | Must equal the directory name. |
| `tier` | `draft` for a contributed scenario. `smoke`, `core`, `live` are set by an engineer once it is trusted. |
| `run_order` | Unique across the tier; scenarios run in this order. |
| `fixture.dataset` | `grain_trap` or `zero_row_optional`. Data is generated from `seed`, never copied from production. |
| `fixture.plant` | The defect deliberately seeded into the data. |
| `turn_budget` | **Exactly** the number of turns in the answer sheet. A test enforces this. |
| `phase_map` | Turn number to phase number, 1 to 7. |
| `persona` | A file under `_personas/`. See below. |
| `gates` | Which checks run. `follow-up.kind` names the drill. |
| `gold` | Paths to the truth files. |
| `required_plants` | Plants that must fire, or the run grades nothing. |

## answer-sheet.yaml

This is the operator's script and everything it knows.

- `opening_message` — the contributor's own vague first words, verbatim.
- `turns` — a list. A plain string is an ordinary turn. A mapping can declare:
  - `substitute_reply: false` — send this exact line, never a matcher reply.
    **Use this for every question the scenario grades.** An ask that gets
    replaced is an ask that was never made.
  - `approval: true` — transmitting this turn *is* the approval of record.
- `ground_truth` — the facts the operator can reveal when asked. Each has
  `terms` (the words in an agent's question that should trigger it) and `fact`
  (what the operator then says).
- `driver_forbidden_terms` — vocabulary the agent must discover for itself. The
  operator is forbidden from using these words. Required if the scenario will
  ever be run with a model-driven operator.

Give the agent room. A live agent needs several turns to author a spec,
build, and self-check. A scenario that asks for results one turn after approval
grades nothing, because there is nothing built yet to grade.

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

## Rules that are easy to get wrong

- **`turn_budget` must equal the turn count.** Not a ceiling.
- **Graded asks need `substitute_reply: false`.** Otherwise the matcher may
  replace the question the scenario exists to ask.
- **The approval turn is never substituted or authored.** Its text becomes the
  approval of record.
- **An event's `trigger_turn` moves when you insert turns above it.** Check it
  after any renumbering.
- **Every gold value comes from the seeded generator**, never from a real
  system.
