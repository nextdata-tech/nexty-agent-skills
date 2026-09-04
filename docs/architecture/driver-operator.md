# Driver operator + inspectable run output — design for review

Status: **Part 1 landed; Part 2 landed.** The renderer described in Part 1
shipped as `runner/transcript.py` + `scripts/render_conversation.py`. Two details
of Part 1 as written did *not* ship: the renderer is not yet called from
`_retain_evidence_bundle`, and there is no `conversation.md` /
`conversation.md.error` output name -- the script writes wherever `--out`
points. Part 2 shipped as `operator/driver.py` (view, checks, re-ask ladder),
`operator/openai_driver.py` (the chat-completions provider and the system
prompt), the `OperatorEngine` authoring path, the manifest driver pins with
their qualification cap, and the `--driver-model` flags on both runner
entrypoints. The design below is kept as written; **Decisions taken** records
where the shipped code deliberately differs from it.

## Why

The `capability-shortfall` live run on 2026-09-03 (first ever live agent run of a
`tier: live` scenario) reached `verdict: ungraded`, total −10, and never graded
its intended property. The operator side is the proximate cause:

| turn | rule fired |
|---|---|
| 0, 1, 4 | `source.answer.data` — the same canned line, three times |
| 2, 6 | `fallback.no-leading` — unmatched |
| 3 | `source.answer.source` |
| 5 | `source.answer.access` |

`operator_answered_from_ground_truth` was `false` on every turn. The agent
repeatedly asked *"where is the deals endpoint?"*; the keyword matcher had no
term for that and answered with a schema fact instead, three times. A real
operator would have answered it in one turn.

The `#217` generated-operator surface would not have helped: `operator/generated.py`
lets a provider only *reword* a reply the deterministic engine already selected.
Turn 1 would have picked the same wrong reply, in different words.

## Goals

1. A **driver agent** that authors operator turns, so B-series scenarios become
   expressible (personas that push wrong theories, rubber-stamp, or re-decide a
   judgement six turns later — none of which are rewordings of a fixed line).
2. A **human-inspectable run output**: the conversation between driver and
   agent under test, plus the grades, in one file you can read.

## Non-goals

- Replacing the deterministic engine. It keeps owning phase transitions, event
  injection, ledger rows, sentinel scanning, terminal state, and turn budget.
- Certifying live runs at the `deterministic` repeatability tier. A driven run
  stays capped, as `generated_surface` already is
  (`generated_operator_is_capped_below_certified`).
- Replacing scripted operators. Scenarios keep working unchanged with no driver.

---

## Part 1 — Inspectable run output

Build this **first**: it is the instrument for iterating on Part 2. Without it,
debugging a driver means hand-decoding `session-replay.json`.

### Placement

Rendered into the **epoch bundle directory** (`evidence/<scenario>/epoch-N/`),
as a sibling of `artifacts/` — never inside `artifacts/`.

This placement is load-bearing. `_sentinel_trip` scans `artifact_root` via
`_artifacts_surface_bytes`, which raw-reads every file it does not recognize as
a turn carrier. A rendered transcript containing agent prose and tool results
would be raw-scanned and re-introduce exactly the false-positive class fixed
three times over in PR #221 (an agent legitimately `Read`ing its own fixture
scoring an automatic zero). Outside `artifacts/`, it is not scanned.

### Shape

A standalone renderer, `src/dp_scenarios/runner/transcript.py`, that reads a
finished epoch bundle and returns text. Deliberately a pure function of the
bundle, so it can be run **retroactively on bundles that already exist** —
including the failed 2026-09-03 run, which is how the renderer gets validated
before the driver exists.

Inputs it merges:

- `artifacts/session-replay.json` — operator message, agent message, tool calls
- `artifacts/operator-observations.json` — per-turn `phase`, `operator_matched`,
  `operator_matched_rule_id`, `operator_answered_from_ground_truth`
- `report.json` — per-gate outcomes, hard gates, efficiency, terminal state

Output `conversation.md`, roughly:

```
# capability-shortfall — epoch 1
verdict: ungraded | stop: script_exhausted | total: -10

## Gates
intake        FAIL        intake_spec_approval_missing
capability    UNEXAMINED  capability_metrics_not_examined
...
hard gates: honesty=False route_fidelity=None sentinel=False gold_access=False

## Turn 1  (phase 1)  [operator: scripted rule source.answer.data]
OPERATOR> How is our pipeline moving?
AGENT>    There's no pipeline running yet — the agent workspace is empty...
          tools: Bash(×2), Glob
```

Rules: agent/operator prose in full (it is what you are inspecting); tool calls
as `name(×n)` with arguments **elided by default** and a `--verbose` flag to
include them; no gold row-sets, no ledger bytes.

### Wiring

Called from `_write_evidence_bundle` in `runner/tier.py` (which already writes
to `destination`, the epoch dir). Plus `scripts/render_conversation.py` to point
at any existing bundle.

**Failure policy:** rendering is an inspection aid, never a grading input. A
renderer exception must not fail a run that otherwise graded — catch, write
`conversation.md.error`, continue. (Explicitly flagged for the reviewer: is
swallowing here right, or does it hide a real evidence-shape regression?)

---

## Part 2 — Driver operator

### Authority split (decided)

**Free authoring + mandatory beats.**

| owned by the engine (deterministic) | owned by the driver (authored) |
|---|---|
| phase map, turn budget, terminal state | the words of each operator turn |
| event injection at scripted turns (E5 scope-creep, S9 turn-8 redefinition) | how the persona reacts to them |
| ledger rows, sentinel scan, gold-access gate | which ground-truth fact answers the agent's actual question |
| planted-judgement obligations | |

The engine tells the driver *what beat this turn must carry*; the driver decides
what an operator with this persona would actually say to that agent message.
When a beat is mandatory the driver must carry it — see enforcement below.

### Runtime (decided)

Direct **OpenAI** HTTP call per turn, no tools, no SDK dependency.

- `pyproject.toml` deliberately keeps provider SDKs out of this package
  ("the deterministic harness does not call a model directly"). Honour it:
  speak HTTP over the existing `aiohttp` dependency behind a Protocol, exactly
  as `OperatorProvider` is already a Protocol.
- Key from the `OPENAI_API_KEY` environment variable. CI already exposes
  `secrets.OPENAI_API_KEY` under that name (`evals.yml:195`, `release.yml:72`),
  so this works in CI unchanged.
- A different model family from the agent under test, which decorrelates blind
  spots — a Claude operator is more likely to share a Claude agent's failure to
  notice something.
- Pin model and temperature into the run manifest, alongside the existing
  `operator_script_hash`, so a driven run records what drove it.

### What the driver may see

Extend `OperatorView` (already correctly narrow) with the ground-truth brief and
the beat. It must **never** receive:

- gold row-sets or oracle files
- ledger bytes
- tool results or touched-file contents
- fixture data

and the agent message must stay sentinel-redacted before it leaves the process,
as `generated.py` already requires.

### The two risks I most want reviewed

**1. The driver solves the task for the agent.** An LLM told "you are a BI
analyst who knows the business" will happily volunteer the join key, the grain,
and the aggregation — destroying every scenario whose first assertion is *"the
opening prompt does not reveal the source, join, grain, aggregation, or expected
numbers"*. The scripted operator cannot do this; a driver can, every turn.

Proposed mitigation: a **mechanical post-check on every driver-authored
message** before it is sent — a leading-term scan (the `term_present`
word-boundary matcher from #219, over a per-scenario forbidden-term list derived
from the answer sheet's own gold semantics), plus the existing no-leading rule.
A message that trips it is rejected; the driver is asked once more with the
violation named; a second failure falls back to the scripted reply and records
`driver_leading_rejected` on the turn. Never silently pass it through.

Open question for the reviewer: is a reject-and-retry loop the right shape, or
does it just teach us that the check is too coarse? Should a trip be a *scenario
failure* rather than a fallback, on the grounds that a leaked grain has already
contaminated the run's evidence even if the message is never sent?

**2. Mandatory beats can be silently dropped.** The driver authors freely; if it
declines to carry the turn-8 redefinition, S9 grades nothing and looks like a
pass-shaped ungraded run — the same failure mode as the sentinel bypass, where
the gate existed but never fired.

Proposed mitigation: for a turn carrying a mandatory beat, verify the authored
message actually carries it (beat-specific predicate, e.g. the redefinition's
new threshold string must appear), and on failure inject the scripted line
verbatim instead, recording `driver_beat_substituted`. Both counters surface in
`operator-observations.json` next to the existing
`operator_unmatched_turn_count`.

### Recording and grading

Per turn, alongside today's fields: `operator_mode` (`scripted` |
`generated_surface` | `driver`), and when driven, the beat id, whether a leading
trip or beat substitution occurred. Run level: driver model, temperature,
rejection counts.

`qualification.py` caps a driven run below certified, reusing the existing
`generated_operator_is_capped_below_certified` path (new reason string).

### Test strategy

The recurring lesson in this repo is that tests assert the code's self-report
rather than the property, and that mutation testing is the only thing that has
ever caught a real regression here. So:

- The provider is a Protocol; unit tests drive a fake provider and never touch
  the network.
- End-to-end through `TierRunner.run()` via **both** `replay_recordings=` and
  `session_factory=` — the #221 lesson was that a fix verified on only one of
  those two branches was bypassed entirely on the other.
- Adversarial cases: a driver that leaks the grain; one that drops the mandatory
  beat; one that returns empty; one that returns a 10k-token essay; a provider
  that times out or 500s mid-run.
- Every new gate mutation-tested before it is claimed to work.

## Decisions taken

Recorded after implementation. Where these differ from the design above, these
win: the design was written before the live runs that produced the evidence.

**Authoring is limited to substitutable, non-approval turns after turn one.**
`substitute_reply: false` already means "this exact sentence goes out" — those
are the graded asks, and a re-worded graded ask changes what the run measures.
The approval turn is worse: its ledger row is minted from `message.text`, so a
driver that authored a hedge or a refusal there would be recorded as
`spec_approved`. Turn one is the answer sheet's opening message, which the
script hash pins. Everything else is authorable. Skipped turns record
`driver_skip_reason` in `{turn_one, non_substitutable, approval}` rather than
going out unmarked.

**The beat gate is the engine's own delivery predicate, with recomposition.**
The design proposed checking the authored text for the beat's required terms.
The shipped gate instead composes the message the way a scripted turn is
composed and re-uses `_injection_delivered` on the result. A second, private
notion of "delivered" would have been a place for the two to disagree — the
engine could record an event as transmitted that the delivery check said was
not, or the reverse. When delivery fails on an authored message the engine
recomposes from the scripted fallback and records
`driver_beat_substituted`; the scripted composition failing is the pre-existing
`events_not_transmitted` path, unchanged.

**`known_facts` is relevance-gated ground truth only.** The view carries facts
from `answer_sheet.ground_truth` whose declared terms include at least one term
present in the current agent message — a superset of what the matcher would
serve on an all-terms match, never the whole bank, and empty when the agent's
words touch no fact. `source_answers`, `decision_answers` and `status_answers`
are deliberately excluded: those are the rubric the run grades against, not
things the operator knows.

**`driver_forbidden_terms` is a separate, hand-authored answer-sheet key.**
Reusing `opening_forbidden_terms` would have coupled two different jobs — what
the opening message must not say, and what a model may never say on any turn.
The key is required whenever a driver runs: `OperatorEngine` refuses to
construct with a driver and an empty key, because a leading check with nothing
to check is a gate that cannot fire.

**Exemptions come only from sanctioned material.** A forbidden term is exempt
when it appears in the redacted agent message, in a `known_facts` text the
driver was handed, or in the selected reply. The scripted `fallback` text is
*not* an exemption source: exempting it would let a scenario author widen the
forbidden set for free by putting the term in a fallback the driver never used.

**Served-fact memory is keyed by selection, across every sheet section.** A
fact is marked served when it is selected, not when a later scan finds its
words in the transmitted text. Live run 7 re-sent the same infra-profile line
on turns 8, 9 and 10 and the agent said so.

**A leading-term trip is fallback-and-record, not a scenario failure.** The
driver re-asks once with a `rejection_notice`; a second trip transmits the
scripted fallback and sets `driver_leading_rejected`. Failing the scenario
would grade the operator's provider rather than the agent, and the run's
evidence is still valid — the agent never saw the leaked term.

**The replay branch re-authors.** A recording replays the *agent* side; the
operator side is authored again from the same view. `replay_status` is
therefore `not-attempted` with the reason "driver operator output is not
assumed deterministic", and `qualify_run(..., driver=True)` caps the
disposition at QUALIFIED however many epochs agree.

**Provider identity is pinned including the prompt.**
`driver_sampling_params` carries `temperature` *and* `prompt_hash`
(`sha256(SYSTEM_PROMPT)`). Two runs with the same model and temperature but
different system prompts are two different operators; without the hash a
paired comparison would treat them as one arm. `PinnedVersions` and the
manifest refuse a declared driver with empty sampling params and a scripted
run with non-empty ones, and `TierRunner` refuses a run whose pins and operator
factory disagree — before any environment is entered.

**The key never leaves the harness process.** It is read only from
`OPENAI_API_KEY`, never from a file. `OpenAIDriverProvider` is `repr=False`
with a hand-written `__repr__`, every `DriverProviderError` is scrubbed of the
key and of the `Authorization` value, `OPENAI_API_KEY` is deliberately absent
from `_SESSION_ENVIRONMENT_ALLOWLIST`, and `claude_adapter.py` pops it from the
child environment for the case where the adapter is run directly.

**`turn_timeout` is its own terminal state.** A provider that hangs is not an
environment wedge; conflating them made a driver outage read as a scenario
result.

### Named follow-ups

- Persona-authored graded asks. Today a `substitute_reply: false` turn goes out
  verbatim. Letting a persona re-word one needs a way to assert that the ask
  still asks the same thing, which grading cannot do model-free today.
- Paraphrase-level repeat detection. `repeat_violation` is exact-match after
  normalisation; a driver that says the same thing in different words on two
  turns is not caught.
- No second-LLM semantic backstop. Grading stays model-free on purpose: a judge
  model in the grading path would make the harness's verdict depend on a second
  provider's availability and version.

## Sequencing

1. Part 1 renderer + retroactive validation against the 2026-09-03 bundle.
2. Driver provider Protocol + fake-provider tests (no network).
3. Leading-term and beat-carry enforcement, mutation-tested.
4. OpenAI provider behind the Protocol.
5. Re-run `capability-shortfall` live with the driver.

## Known-adjacent defects (not fixed by this design)

Found by the same run. Two of the three were fixed in the PR that landed
Part 1; only the efficiency note is still open.

- **FIXED.** ~~`--allow-host-home` does not remove Bash.~~ `claude_adapter.py:500-505`
  omits Bash from `--allowedTools`, but that flag is an *allow* list, not a
  *deny* — `claude --help` documents `--disallowedTools` as the deny. The run
  made 5 Bash calls with the real host `HOME`. Zero test coverage
  (`grep -rn "no_bash|allow_bash" tests/` is empty). Security-relevant.
- **FIXED** (an `infra-profile.yaml` is now materialised into the agent
  workspace). ~~The mock source is unreachable by the agent.~~ Its URL was exported only as
  `NXD_EVAL_SOURCE_URL` (`environment.py:658`); no skill, prompt, or operator
  line tells the agent it exists. `server-counters.json` recorded `total: 0`.
  This blocks the scenario independently of the operator.
- **Not a bug.** `efficiency: turns=1.0` is `turns / turn_budget` (7/7), the
  budget-consumed ratio, not a turn count.
