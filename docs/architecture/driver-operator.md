# Driver operator

The operator is the side of a `dp-scenarios` run that plays the human. By
default it is scripted: a keyword matcher selects a canned reply per turn. A
**driver** replaces the *words* of a substitutable turn with text authored by a
model, so the agent under test faces a persona that reacts rather than a fixed
answer bank. Everything that decides what a run *means* stays deterministic.

Enabled with `--driver-model` on `scripts/run_local_claude.py` or
`dp_scenarios.runner.cli` (the latter requires `--mode live`; replaying a
recording re-authors nothing).

## Authority split

| Owned by the engine (deterministic) | Owned by the driver (authored) |
|---|---|
| phase map, turn budget, terminal state | the words of each operator turn |
| event injection at scripted turns | how the persona reacts to them |
| ledger rows, sentinel scan, gold-access gate | which ground-truth fact answers the agent's actual question |
| planted-judgement obligations | |

The engine tells the driver which beat a turn must carry; the driver decides
what an operator with this persona would say to that agent message.

## Which turns are authorable

A turn is authorable when a driver is configured, it is not turn 1, the script
marks it `substitute_reply`, and it is not an approval turn. An approval turn
transmits its declared line verbatim on every provider path, because the
transmitted text becomes `operator_approval_text` and therefore the
`spec_approved` ledger row's `artifact_ref`; substituting a matcher reply there
would record an unrelated sentence — or a refusal — as the approval.

## Runtime

A direct OpenAI chat-completions call per turn, over the existing `aiohttp`
dependency behind a Protocol, with no provider SDK and no tools. The key comes
from `OPENAI_API_KEY` in the environment and nowhere else: there is no file
fallback and no flag that takes a key. It is absent from the agent session's
environment allowlist and popped from the Claude adapter's child environment,
so the agent under test cannot read it; the provider's `repr` and every provider
error are scrubbed of both the key and the `Authorization` header.

Using a different model family from the agent under test decorrelates blind
spots — an operator sharing the agent's lineage is likelier to share its failure
to notice something.

The request always sends `max_completion_tokens`; GPT-5-class models reject
`max_tokens` outright and older models accept the newer name, so one shape
serves both. `temperature` is omitted when it is the API default (1.0), which
those models require, and sent otherwise.

## What the driver may see

`DriverView` extends the deliberately narrow `OperatorView` with the
ground-truth brief and the turn's beat. It never receives gold row-sets or
oracle files, ledger bytes, tool results, touched-file contents, or fixture
data.

The agent message is sentinel-redacted before it leaves the process. The
redaction set is the union of the operator script's own sentinel, the sentinels
of live event cards, the generated fixture manifest's markers, and every marker
a scenario's gates declare (`scenario.declared_sentinels`). The manifest alone
is not the inventory: `capability-shortfall` declares `operator.sentinel: null`
and plants its graded `pii_sentinel` in the mock-source route table, which
`marker_values` never reads.

Redaction is symmetric. Authored text that repeats a planted marker is rejected
by the same ladder that catches an obstacle, so nothing planted leaves in the
operator's own turn either — otherwise it would re-enter the provider context as
a prior message on every later turn.

## Enforcement

Two properties a free-authoring operator can destroy, each checked mechanically
before a message is sent.

**Leading.** A model told it is an analyst who knows the business will volunteer
the join key, the grain, or the aggregation, defeating any scenario whose first
assertion is that the opening prompt reveals none of them. Every authored
message passes a word-boundary scan over the scenario's `driver_forbidden_terms`
(required: the engine refuses to construct a driver without them). Terms the
agent has already used itself are exempt, so the operator may answer a question
in the agent's own words.

**Mandatory beats.** A driver that declines to carry a scripted beat leaves the
scenario grading nothing while looking like a clean run. The authored message is
checked for the beat, and after composition the engine's own delivery predicate
gets the final word.

Both use the same ladder: a violation is named back to the provider and it
authors once more; a second failure falls back to the scripted line. A rejected
call is a **fallback, not an abort** — the run completes and spends the full
agent budget either way — so the per-epoch summary states whether the driver
authored every substitutable turn or fell back, and the fallback reason carries
the provider's own scrubbed message.

## Recording and grading

Per turn: `operator_mode` (`scripted` | `generated_surface` | `driver` |
`driver_fallback`), the beat id, and whether a leading trip, repeat rejection or
beat substitution occurred. Per run: driver model, temperature, completion cap,
prompt hash, and the rejection counters.

The manifest pins the model and `driver_sampling_params` — temperature,
`max_tokens` and the prompt hash. Two runs differing in any of them are two
different operators and must not pair for repeatability.

**A driven run is capped at QUALIFIED.** A model authored the operator's words,
so nothing on the operator side is reproducible turn-for-turn: `replay_status`
is `not-attempted` and the disposition can never reach CERTIFIED, however many
epochs agree.

`driver_repeat_rejected_count` is keyed to the engine's own selections
(`prior_base_texts`), not to transmitted text. On a driven run those diverge, so
it fires when the driver reproduces a scripted line verbatim and not when the
driver repeats itself.

## Served-fact memory

`served_reply_keys` records a ground-truth fact once it has actually been
transmitted, so the operator does not restate it. Selection is not
transmission: a reply picked on the turn before a `substitute_reply: false`
ask, or before an approval turn, never goes out, and marking it would suppress
an answer the agent has still never been given.

Under a driver the scripted sentence never goes out, so transmission is decided
by whether the authored turn carried the reply's substance. That is measured
deterministically from the reply's distinctive words — its own content, minus
everything already in the agent's message:

- fewer than three distinctive words: never counted as conveyed, because the
  reply adds too little beyond the question to judge either way;
- three: every one must appear, since at that size any two give 0.67 and the
  ratio cannot discriminate;
- four or more: at least three of them, and at least a third.

The three-word minimum is what covers four and five distinctive words, where a
ratio floor alone still admitted a two-word deflection (0.50 and 0.40, both
above a third); the ratio only becomes the binding condition at six.

The subtraction is what makes it safe. A fact's trigger terms come from the
question, so a driver that merely echoes the agent shares nothing with what
remains and scores zero, which is the deflection case that must not consume the
fact. Consuming on driver success alone would be wrong for exactly that reason:
a driver may deflect while succeeding, and since only a `fresh_session` card
clears the set, that would stonewall the agent for the rest of the run.

Calibrated against real driven turns: genuine restatements scored 0.45–0.89,
deflections and bare echoes scored 0.00. Leaving this unmeasured kept the memory
empty for a whole driven run — a live 15-turn run re-selected one fact ten times
and another six, with zero suppressions, while the agent answered "already done"
four turns running.

## Test strategy

Tests in this package assert properties, not the code's self-report, because
mutation testing is the only thing that has ever caught a real regression here.

- The provider is a Protocol; unit tests drive a fake and never touch the
  network.
- End-to-end runs go through `TierRunner.run()` via **both** `replay_recordings=`
  and `session_factory=`; a fix verified on one branch has been bypassed
  entirely on the other.
- Adversarial cases: a driver that leaks a forbidden term, drops a mandatory
  beat, returns empty, returns an oversized essay, times out, or 500s mid-run.
- Every gate is mutation-tested before it is claimed to work.
