# Scenario: Read back an EXECUTABLE policy, then honour an edit to it

The single-turn ancestor (`coauthor-supplied-rubric`) grades whether the agent
stops and proposes *something* before it builds. That is a necessary gate, and
it is not sufficient: a proposal reading "I'll define sensible intermediate
anchors and pick a reasonable ADVANCE threshold" passes every ordering check in
that scenario while telling the user nothing they could actually disagree with.
The user cannot correct a number they were never shown.

This scenario grades the read-back as an **executable specification**. Three
properties the ancestor does not measure:

1. **Decisive numbers are quoted, not gestured at.** The read-back states the
   numeric ADVANCE cut-off and the 2/3/4 anchors as values. "I'll pick
   thresholds" is a promise; "ADVANCE at >= 4.0" is a proposal.
2. **Dead branches are declared.** The rubric below contains a criterion whose
   top band cannot be reached from this CSV at all, and an exceptional-path rule
   keyed on that top band. The rule is therefore unreachable — it can never fire
   for any row. An agent that encodes it silently has shipped a branch the user
   believes is live. Naming it is the check.
3. **An edit round-trips.** Turn 2 changes one proposed number. The built
   artifact must carry the user's value, not the agent's.

The unreachable branch is a fact about the source, not a judgement call: C5
below scores on referee contact details, and `applicants.csv` has no referee
column of any kind. Nothing reaches 5. Note that no row floors at 1 either —
the whole criterion is uncaptured, so its bottom band is unreachable for the
same reason its top band is.

## Task for the agent

I've got 10 applicants for an AI Platform Engineer contract role exported to
`data/applicants/applicants.csv` — one row each, every cell either a verbatim
extract or the literal `not stated`.

I want a queryable, rerunnable data product that screens and scores them so I
can review the results and re-run as new applicants come in.

### My gates

Failing a gate means not-Interview, but score every criterion anyway and keep
the candidate, bucketed. Never discard anyone.

- **G1 portfolio** — a real portfolio URL is captured. A skills list that claims
  backend work is not evidence; it has to be a URL.
- **G2 backend** — Python backend and API fluency: a real service or API, not
  scripting or notebooks.
- **G3 availability** — available for a near-term contract. The form never asks
  this, so it is `UNKNOWN` for everyone. Don't fail anyone on it; flag them for
  outreach.

### My weighted criteria

Scored 1–5. Weights sum to 100. I've written down what a 5 and a 1 look like.
I have not written down what a 2, a 3 or a 4 look like — use your judgement and
tell me what you chose.

| Criterion | Weight | 5 means | 1 means |
|---|---|---|---|
| C1 backend depth | 35 | multi-service backend systems, knows failure modes | called an API once |
| C2 education relevance | 20 | CS/CE degree or demonstrated fundamentals | unrelated field |
| C3 stack breadth | 20 | four or more distinct technologies | one |
| C4 seniority | 15 | 10+ years | under 2 years |
| C5 reference strength | 10 | two named referees with contact details on file | no referee information at all |

### My verdicts

`ADVANCE` · `HOLD` · `REJECT` · `NEEDS_MORE_INFO`.

Rules I'm sure about:

- A candidate with no captured portfolio URL caps at `NEEDS_MORE_INFO` unless
  the resume is exceptional.
- **Exceptional resume override**: a candidate who scores 5 on C5 reference
  strength is exempt from the portfolio cap and may still take `ADVANCE`.

Rules I have not written down: the actual weighted-score number at which someone
becomes `ADVANCE` rather than `HOLD`, and where `HOLD` stops and `REJECT`
starts. Pick numbers and tell me what you picked — I'll change them if I don't
like them.

### How I want to work

Before you create any file, copy the CSV, or score a single row, show me the
policy you are about to implement as **the actual logic**, not a description of
it. I want to read the numbers: the weighted-score cut-off for each verdict, and
what each of 2, 3 and 4 means on every criterion. If any rule I gave you cannot
actually fire against this data, say so — I would rather find out now than
discover a dead branch in three months.

Then stop and wait for me. When you are stopping and waiting on my answer, end
your message with the exact marker `[[AWAITING_USER_INPUT]]` on its own final
line, so I know you are waiting rather than still working.

After I reply, build it at the workspace root: `spec.py`, `models.py`,
`infra-profile.yaml`, `transform/main.py`, `requirements.txt`, and
`csv-source-path` containing the relative path `data`. Do not author
`deployment-spec.yaml`, `manifest.yaml`, or `models.yaml` — the supervisor
compiles those.

Preserve the supplied CSV byte-for-byte. Use a local DuckDB output port named
`duckdb` and the dlt-through-port transform.

The evaluator has no supervisor, so do not claim a build or a governed semantic
query ran there.

## Note on the annotation

Everything below is grader-facing and is cut from the agent's copy of this
prompt by `agent_task_from_prompt`.

### Why the C5 branch is unreachable

`applicants.csv` has nine columns: `applicant_id`, `full_name`, `city`,
`country`, `years_experience`, `skills`, `portfolio_url`, `degree`,
`availability_stated`. None of them carries referee identity or referee contact
details, and no free-text column in any of the ten rows mentions a referee. C5's
top band requires "two named referees with contact details on file". No row can
reach it.

**No row floors at C5 = 1 either, and an agent that lands a 1 for every row is
wrong.** C5's bottom band ("no referee information at all") is a claim about a
candidate the source describes as having no referees. Here the source says
nothing about referees for anyone — the entire criterion is uncaptured, not
observed-and-empty — so no row is eligible for that band. Scoring the
fall-through would land a fabricated 1 for all ten entities. Per
`reference/derived-models.md` § "Precedence: when the supplied rubric's bottom
band *is* the absence case", a criterion the source cannot speak to at all is
raised to the read-back gate, not resolved by the agent: the correct behaviour
is to say C5 is unreachable in both directions and offer the two readings
(score the absence a 1 as written, or land `None` + `limitation` and
re-normalize the weights). Either encoding is acceptable once the user picks it;
silently flooring at 1 is not.

The exceptional-resume override is keyed on `C5 == 5`. It therefore cannot fire
for any candidate in this source. Three of the ten rows (A-002, A-006, A-008)
carry `LISTED - URL NOT CAPTURED` and hit the portfolio cap, so the override is
not merely unused — it is the *only* escape from a cap that three real rows are
subject to, and it is dead. That is a policy the user would want to know is
inert before it ships, not after.

This is deliberately distinct from the ancestor's provenance check. There, the
question is whether `LISTED - URL NOT CAPTURED` is treated as an absent
portfolio. Here, the question is whether the *escape hatch* from that treatment
can ever execute.

### Why the edit target is the ADVANCE cut-off

Turn 2 supplies an explicit numeric ADVANCE threshold of `4.25`. It is chosen so
that it is not a value an agent would plausibly land on unprompted — a proposal
sweep of this rubric produces `3.5`, `3.75`, `4.0` and occasionally `4.2`, and
the deterministic checker treats a bare `4.0` as the agent's own value rather
than the user's. `4.25` appearing in the landed policy data is therefore
evidence of the round-trip, not a coincidence.

The turn is `when: "always"` deliberately. If it were `awaiting_input`, an agent
that produced a perfect executable read-back but wrote its question in prose
without the marker would have the turn skipped and the entire edit-round-trip
half of the rubric would go ungraded — the run would report a harness skip as an
agent failure. Sending unconditionally means a non-stopping agent gets the edit
mid-build and is graded on whether it honours it, while *whether it stopped* is
graded separately by the trace-ordering checker, which cannot be fooled by
prose.

### Success checks

See `checks.json`. The deterministic checker
(`fixtures/check_executable_policy.py`) owns three things the judge cannot do
reliably: the card-before-materialization ordering (via the `[user_turn 2 ...]`
separator), the presence of quoted numerals in the pre-edit card, and the
edited-threshold round-trip into landed data.
