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

## What the operator's turn is for

Most turns have no declared answer behind them. The engine resolves what such
a turn is *for* into one `directive`, and that value -- not a stock sentence --
is what the driver is given.

| directive | when | what the operator does |
|---|---|---|
| `answer` | the matcher resolved a declared answer | say that substance in its own words |
| `yield` | the agent asked for nothing | acknowledge and hand the floor back |
| `unknown_fact:<gap_stance>` | a source question with no declared answer | scenario decides: the source is short, or the operator is merely uninformed |
| `unknown_fact:operator_is_uninformed` | a status or miscellaneous ask | fixed: "is it done on your side?" is not a claim about what the source holds, so the scenario's stance does not apply |
| `decision:<stance_when_unknown>` | a decision, an approval, or any message using choice vocabulary | persona decides the tactic |

A choice outranks the classification. The rule bank is first-match-wins with
`source.question` first, and that rule fires on `data|field|row|table|input` --
vocabulary too common to be evidence of anything -- so "Which path should I
take? Both are in the data." arrives classified as a source question.
Answering it with "I do not have that" leaves the choice unmade, which is the
stall the whole change exists to remove.

A **repeat-suppressed** turn resolves as though nothing were declared. The
fact exists but has already been given, so the turn has no substance to
convey; treating it as `answer` handed the driver an empty `selected_reply`
the prompt promises is full, which is an invitation to invent one.

It is a cross product on purpose, and the axes are **not** symmetric. The
scenario owns what a gap *means* here, because only the answer sheet can be
checked against the gold the run is graded on. The persona owns the tactic for
handing a decision back, because that is voice and carries no factual claim.
`confidently-wrong` is the standing counter-example: its reply bank holds
factual claims ("The API is down"), which is why a stance is a tactic rather
than another canned sentence.

`answer` is the only directive under which `selected_reply` is non-empty.
Passing a persona bank line there is what produced the failure this replaces:
the prompt says a non-empty `selected_reply` is the substance the turn
expects, so the driver faithfully paraphrased "I am not deciding that." A live
15-turn run refused on eight turns, four of them turns where the agent had
asked for nothing at all, and the run made a third of the tool calls of
comparable runs and never built the product. Nothing tripped, because the
driver was doing exactly what it was told.

**The yield rule is not driver-specific.** `base` fell through to the scripted
turn only when the matcher returned nothing, and the matcher always returns
something, so an author's room turns -- `Keep going, please.` / `Take your
time.` -- were unreachable text on the scripted, generated-surface and driven
paths alike. The scripted operator answered a status update with a refusal
too.

That also means a substitutable turn's text is now script identity, and
`operator_script_hash` covers it. It used to be elided on the premise that
such text is never transmitted; two scripts differing only in a room turn
therefore hashed identically while sending different bytes, so the change
described above as "a benchmark-pairing break" would not have broken any
pairing at all.

## What the driver may see

`DriverView` extends the deliberately narrow `OperatorView` with the
ground-truth brief, the turn's beat and its directive. It never receives gold
row-sets or oracle files, ledger bytes, tool results, touched-file contents, or
fixture data.

The brief is offered **whole**, every turn. It was previously filtered by
keyword-matching each fact's `terms` against the current agent message, which
starved the driver exactly when a question was phrased unexpectedly: one live
run was handed no fact at all on four turns and the same single fact on four
more, because one trigger term happened to be a common word. A fact's `terms`
trigger the *question*, so gating the offer on them asked whether the agent had
used the author's vocabulary, not whether the operator knows the answer. What
must not happen is the operator *volunteering* an unasked fact, and that is a
prompt rule.

Relevance still gates one thing: **which forbidden terms are exempt.** A term
is exempt when the agent has already used it, or when it appears in a fact the
agent actually asked for -- answering in the asker's own words is not leading.
"Asked for" means the fact's *whole* declared term set is present, mirroring
`answer_for_ground_truth`: a fact keyed on ("exact", "sitting", "stage") is not
the answer to a message that merely says "stage". Exempting from every
*offered* fact instead would retire `driver_forbidden_terms` the moment the
brief widened, silently: the scan would still run with nothing left in it.

In practice that relevance test contributes little on its own, because a fact
whose whole term set is present has usually already been *selected*, and the
selected reply is exempt anyway. It earns its place on the two paths where it
has not: a repeat-suppressed re-ask, where there is no selected reply, and a
turn where a decision rule or a sort-earlier fact won.

This puts a requirement on the scenario. A fact that resolves the drill must
have its vocabulary declared in `driver_forbidden_terms`, or the widened offer
leaves nothing guarding it -- `capability-shortfall` declares `updatedat` for
exactly this reason.

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
everything already in the agent's message. At least three of them must appear,
and at least a third. Fewer than three
distinctive words is never counted as conveyed: the reply adds too little
beyond the question to judge either way.

The three-word floor is what does the work almost everywhere. A ratio alone
admitted a two-word deflection at four and five distinctive words (0.50 and
0.40, both above a third), and the ratio only becomes the stricter of the two
at nine, where a third first exceeds three.

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
