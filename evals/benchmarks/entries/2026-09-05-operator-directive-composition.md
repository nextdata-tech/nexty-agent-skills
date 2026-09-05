---
id: 2026-09-05-operator-directive-composition
date: 2026-09-05
label: "evals: the operator's turn has a directive composed from persona and scenario"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — the operator's turn has a directive composed from persona and scenario

## Notes

**No arm, deliberately, and the paired live runs below must not be read as
one.** This change is to the harness that measures skills, not to any skill.
It ships no change under `src/`, so no scenario can distinguish it in the sense
the ledger means: nothing about the pack got better.

Two live `capability-shortfall` driver runs bracket the change and are worth
recording as diagnosis, not as a result:

| | before | after |
|---|---|---|
| dead-end operator refusals | 8 of 15 turns | 0 |
| agent tool calls | 66 | 226 |
| ground-truth answers served | 5 | 6 |
| capability gate | not examined | PASS |
| construction gate | not examined | PASS |

The agent did roughly three times the work, but **the agent did not improve** —
it was previously being stonewalled. Reading that 66 → 226 as a pack
improvement would put a number in the ledger that measures the instrument and
labels it the subject, which is why this entry carries no record.

What shipped. Under a driver, the engine passed the matcher's selected reply
as `selected_reply`, and the authoring prompt says a non-empty `selected_reply`
is "the substance the conversation expects from you here". The matcher always
returns something, falling back to a persona bank line, and every shipped
persona's bank is a refusal for the categories that matter — all seven share
the byte-identical fallback `"I don't know, you tell me."`. So the driver was
faithfully paraphrasing scripted refusals, including on turns where the agent
had asked for nothing at all. Nothing tripped, because the operator was doing
exactly what it was told.

The replacement is a composition rather than a bigger fact bank. The scenario
owns what a gap *means* here (`gap_stance`), because only the answer sheet can
be checked against the gold a run is graded on; the persona owns the tactic for
handing a decision back (`stance_when_unknown`), because that is voice and
carries no factual claim. `confidently-wrong` is the standing reason the axes
must stay asymmetric: its bank holds factual claims ("The API is down"), which
under the old wiring the driver would have asserted as its own.

Three defects found in review are worth recording because each was silent.
Discarding the match on a repeat-suppression made a suppressed turn resolve as
`answer` with an empty `selected_reply` — substance the prompt promises is
there, which invites invention. Widening the fact offer to the whole brief
removed the only structural guard on `updated_at_meaning`, the fact that
resolves the drill, because `updatedat` was not in `driver_forbidden_terms`
and had never needed to be while the offer was keyword-gated. And
`operator_script_hash` elided substitutable turn text on the premise that it is
never transmitted — false once a yielded turn sends it, so two scripts
differing only in a room turn hashed identically while emitting different
bytes.

One behaviour change reaches the scripted path. `base` fell through to the
scripted turn only when the matcher returned nothing, and it never does, so an
author's room turns — `Keep going, please.` / `Take your time.` — were
unreachable text on every path. Restoring them changes scripted transcripts.

## Evidence

`evals/dp-scenarios/tests/test_operator_directive.py` carries the change: the
composition table, the yield rule on the scripted, generated-surface and driven
paths, the repeat-suppressed directive, the forbidden-term exemption that
survives the widened offer, and the directive's appearance in the ledger claim
and the rendered conversation file.

Twenty-one hand-authored mutants over `engine.py`, `matcher.py`,
`appender.py` and `transcript.py` were run against the suite and all twenty-one
were killed. Three initially survived and produced tests rather than an
argument that they were equivalent: the driver fallback reverting to a stock
line, the forbidden-term exemption loosened from `all` terms to `any`, and a
`_NON_PROSE` fixture that was single-line and therefore asserted nothing about
the multi-line case the guard exists for.
