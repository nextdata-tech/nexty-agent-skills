# `dp-spec.md` — the intermediate representation between intent and closure

## Contents

- [Why this file exists](#why-this-file-exists)
- [Where it lives, and why not in the closure](#where-it-lives-and-why-not-in-the-closure)
- [The three authoring modes](#the-three-authoring-modes)
- [Reading a user-written spec: fill, never silently correct](#reading-a-user-written-spec-fill-never-silently-correct)
- [Frontmatter](#frontmatter)
- [Sections](#sections)
- [What each section compiles to](#what-each-section-compiles-to)
- [The validator](#the-validator)
- [Approval](#approval)
- [Worked example](#worked-example)

## Why this file exists

The loop's Step 1 gathers intent, source, questions and any supplied procedure.
Until now that gathering lived only in the conversation, and the policy read-back
gate stated it back as **prose in a chat turn**. Prose in a chat turn cannot be
diffed, cannot be re-approved, cannot be validated, and does not survive the
session that produced it.

`dp-spec.md` is that same content as a **file the user can read and edit**. It is
the intermediate representation: above it is what the user wants, below it is the
Python closure `nxd-generate-dp` compiles. Everything the generator needs to
author a closure is in it, and nothing else is.

Three things it fixes:

1. **The read-back becomes an artifact.** The gate's obligation — enumerate every
   gate, weight, anchor, band and precedence rule — is discharged by writing this
   file and showing it, not by composing a paragraph. The user corrects a line
   instead of describing a correction.
2. **Gaps become mechanically detectable.** A scale defining only 5 and 1, a
   verdict with no threshold, weights that do not sum, a gate with no `UNKNOWN`
   rule: these are the gap classes the gate fires on, and in a structured file a
   script finds them instead of the agent's attention.
3. **The rulings ledger stops being reconstructed.** `nxd_decisions` rows are a
   projection of this file's `decisions:` block, and `provenance` is recorded at
   the moment a value is written rather than remembered at codegen time. A value
   the user typed is `user_confirmed`; a value the agent added to the spec is
   `agent_authored` and stays so even after approval.

It is **not** a replacement for `CONTEXT.md`. This file is the *input* to
generation; `CONTEXT.md` is the closure's own record of what generation
*produced* — the reopen recipe, the build outcomes, the known blockers. The
generator writes `CONTEXT.md` from this spec plus what actually happened.

## Where it lives, and why not in the closure

```
…/nxd-pocket/<workflow>/
├── dp-spec.md          ← the IR. Beside the closure, not inside it.
└── closure/            ← the generated definition; build_data_product points here
    ├── spec.py
    ├── CONTEXT.md
    └── …
```

**Beside, never inside.** Two reasons, and both matter:

- The policy gate forbids writing **closure** files before approval. The IR must
  be written *to get* approval. Putting it outside the closure directory keeps
  the gate honest: writing `dp-spec.md` is not a materialization, because nothing
  under `closure/` exists yet.
- The IR carries the *whole* conversation — rejected options, open questions,
  the user's own wording. The closure carries only what shipped. Merging them
  would either leak drafting state into a handed-off product or force the IR to
  be sanitized at exactly the moment it is most useful.

The closure stays self-contained regardless: `CONTEXT.md` and any
`contracts/<name>.md` still hold everything a later session needs, and **no
closure file may reference `../dp-spec.md`** — that is precisely the
closure-escaping pointer Phase C fails. The IR is upstream of the closure, not a
dependency of it.

## The three authoring modes

The spec is user-editable, so it arrives in one of three states. All three
converge on the same validated file.

| Mode | What happened | What you do |
|---|---|---|
| **User-authored** | The user hands you a `dp-spec.md`, or a free-form doc that is one (a build spec, a rubric doc, a requirements page). | Parse leniently, map it onto the schema, fill gaps, show the diff. |
| **Agent-authored** | The user described the product conversationally. | Draft the whole file from Step 1's gathering, then show it. |
| **Round-trip** | A spec exists from an earlier session, and the user wants a change. | Edit the file, re-validate, re-approve. A rubric change is a new `rubric_version`. |

A free-form doc is the common case — the user already wrote down what they want,
just not in this shape. **Translate it; do not ask them to re-type it into a
template.** Read the doc, produce the structured spec, and show what you mapped
where. Their prose is preserved verbatim wherever it is a ruling.

## Reading a user-written spec: fill, never silently correct

A user-authored spec is the **specification**, in the exact sense
`derivation-plan.md` means when the user supplies a ruling: encode it verbatim,
value-for-value. Do not improve it, reorder it, or fill a missing case with a
default.

What you may do to a user-written spec:

- **Add** a missing field, marked `provenance: agent_authored`, and say so.
- **Flag** a contradiction or a gap as an open question in `open_questions:`.
- **Normalize** shape only — a table into the schema's list-of-mappings, a prose
  weight "a quarter" into `0.25` — never meaning.

What you may **never** do:

- Change a value the user wrote, however wrong it looks. A weight set that sums
  to 96% is an open question, not a rounding opportunity.
- Delete a section you do not know how to compile. Carry it and flag it.
- Mark your own addition `user_confirmed`. Approval moves `status`; it never
  moves `provenance`.

**Show the diff.** When you fill or normalize anything, state what you changed in
the read-back — "you gave 5 and 1 for C9; I proposed 4/3/2 anchors, marked
agent-authored". The user approving a spec they did not know you edited is the
same unrecoverable failure as skipping the gate.

## Frontmatter

```yaml
---
dp_spec_version: 1              # this schema's version, not the product's
name: candidate_scoring         # the DP name; snake_case, becomes the closure's data_product name
workflow: candidate-scoring     # the stable workflow id — one per data product, forever
status: draft                   # draft | proposed | approved
rubric_version: v1              # required only when `criteria:` or `judgments:` is present
---
```

`status` is the approval axis and only the user moves it to `approved`. An agent
may write `draft` or `proposed`; writing `approved` on the user's behalf is the
gate violation this whole file exists to prevent.

`workflow` is the durable key across sessions — the same id rebuilds the same
product. Never regenerate it for an edit.

## Sections

Section headings are fixed and matched exactly (case-insensitive, `##` level).
Order is fixed too, so a diff between two versions of a spec is readable. An
absent optional section is absent, not an empty heading.

### `## intent` (required)

One paragraph, the user's words: what the product is for and who reads it.

### `## questions` (required)

A list of the natural-language questions the product must answer. These drive
inference right-to-left and they are what the model is judged against. A question
no model answers is a gap the read-back must surface; a model no question
motivates should not be built.

### `## sources` (required)

One entry per source. With 2+, each takes a short distinct label.

```yaml
- label: applications        # omit entirely for a single source
  type: csv                  # csv | file | database | api
  location: ./exports/       # path, host/db, or base URL — never a credential
  scope: |
    The filter that defines the population, verbatim.
  credential_keys: []        # KEY NAMES ONLY. Never a value, in this file or any other.
```

`credential_keys` names which secrets the closure will need so the plan is
complete; the values land only in the generated `infra-profile.yaml`, never here.
This file is meant to be shareable and reviewable — a credential in it defeats
that.

### `## population` (required)

The full population and, if the source is sampled, the exact reproducible
selection rule. A sample rule is a **ruling** and gets a `decisions:` row.

```yaml
population: |
  Every application on job <job_id> whose candidate passed fraud review.
sample_rule: null            # or the exact rule; null means "the whole population"
excludes: |
  What the rule leaves out, and whether any downstream model cares.
```

### `## models` (required)

The model plan, backward-chained from the questions. This is the section
`nxd-generate-dp`'s Step 1a would otherwise derive from scratch.

```yaml
- name: raw_candidates
  kind: base                 # base | derived | view | reference
  grain: |
    One row per application.
  key: [ashby_application_id]
  answers: [q1, q2]          # which questions this model serves; [] for an input-only model
  description: |
    What it is, in one sentence — this becomes the semantic model description.
  fields:                    # optional at draft; required before approval for derived models
    - name: rust_verbatim
      type: string
      role: dimension
      derivation: |
        Verbatim résumé quote, or the sentinel NOT MENTIONED.
```

`kind: reference` is a base model carrying a landed ruling (a rubric table, a
merchant→category map, `nxd_decisions` itself). It is a base model to the
generator; the distinct kind exists so the validator can check it has a
corresponding `decisions:` row.

**Every derived model states its grain and its key** — that is the Gate's
requirement, and stating it here means the generator validates rather than
invents. A derived model whose key is grain-derived says so:
`key: [invoice_id, period]` with the grain sentence naming invoice × month.

### `## gates` (optional)

A gate blocks an outcome without discarding a row. **Every gate must state its
`unknown` handling** — an absent input is a landed `UNKNOWN`, never a `FAIL`, and
the validator enforces that the rule is stated.

```yaml
- id: G1
  name: Shipped an agentic system
  rule: |
    Multi-step agents, tool calling, or orchestration — in production or a
    substantial public repo. A RAG chatbot alone does not pass. Agentic terms
    appearing only in a skills list do not pass.
  unknown: UNKNOWN           # what an absent/unreadable input produces — never FAIL
  blocks: [interview]        # which verdicts this gate blocks when failed
```

### `## criteria` (optional)

The weighted rubric. Present only when the product scores.

```yaml
- id: C1
  name: Agentic AI depth
  weight: 0.25               # fractions; the validator checks the sum
  scale: {min: 1, max: 5}
  anchors:                   # EVERY level between min and max, or the validator fails
    5: Multi-agent systems or agent infrastructure; handled failure modes.
    4: …
    3: …
    2: …
    1: Called an LLM API.
  provenance: user_confirmed # per criterion; an anchor YOU wrote makes it agent_authored
  evidence_fields: [agentic_frameworks_named]   # which source fields may be cited
```

The incomplete-scale gap is the most common one in a hand-written rubric and the
single clearest reason this file is structured: a doc that gives 5 and 1 reads as
complete to a human and is unexecutable. The validator names every missing level.

### `## verdicts` (optional)

The verdict vocabulary with bands and precedence. Required whenever `criteria:`
is present — a score with no mapping to a verdict is a gap.

```yaml
values: [interview, interview_if_repo_verifies, different_role, needs_more_info, pass]
bands:
  - verdict: interview
    min_score: 3.8
  - verdict: needs_more_info
    min_score: null          # reached by rule, not by score
    rule: |
      Any gate UNKNOWN, or scored rubric weight below 0.6.
precedence: |
  Gate failure beats score. UNKNOWN-driven caps beat score bands. A cap keyed on
  absence must name the uncertainty (needs_more_info), never a judgement (pass).
```

### `## judgments` (optional)

Present when any field is produced by an agent reading evidence rather than
computed. This is the **model-generation** record: which model produced the
scores, under which rubric version, with which prompt.

```yaml
- model: candidate_judgments
  produced_by: agent         # agent | user | source
  generator_model: claude-opus-5   # the identity landed in judged_by
  rubric_version: v1
  prompt_ref: prompts/score_candidate.md    # relative to THIS file, not the closure
  evidence_required: true
  reruns: incremental        # incremental | full — incremental judges only unjudged keys
```

`generator_model` is what lands in the judgement rows' `judged_by` column, so
"which model scored this entity" is a query rather than a guess. Two runs by
different models coexist as distinct rows — that is what the four-part key in
`nxd-generate-dp`'s `reference/llm-judgments.md` is for. Reproducibility depends
on this being recorded, because nothing else in the closure carries it.

`reruns: incremental` means a later run judges only `source keys − already-judged
keys` at the current `rubric_version` and appends a new `batch-00N.csv`. A rubric
change is a **new** `rubric_version`, never an in-place edit.

### `## schedule` (optional)

```yaml
trigger: cron                # manual | cron | on_new_data
cron: "0 8 * * *"
timezone: America/Los_Angeles
incremental: true            # requires every promised model be append-safe
cursor_field: created_at
```

`incremental: true` is a claim with teeth — it commits the closure to the one
sanctioned route in `nxd-generate-dp`'s `reference/incremental-transforms.md`,
which gates on every promised model being append-safe. A spec asking for
incremental over an aggregate or regrain model is a gap the read-back surfaces,
not something the generator quietly resolves.

### `## outputs` (optional)

```yaml
- name: scored_candidates
  kind: semantic_port        # semantic_port | static_artifact
  sort: weighted_total desc
  columns: [rank, name, verdict, weighted_total, scored_weight_fraction]
```

Absent this section, the output is the default DuckDB semantic port over every
promised model — which is usually right. State it when the user asked for a
specific shape, ordering, or a static artifact.

### `## decisions` (required whenever any ruling exists)

The rulings ledger, in the exact shape `nxd_decisions` lands. One row per ruling,
both axes always populated.

```yaml
- decision_id: candidate_scoring_rubric
  status: confirmed          # confirmed | proposed | blocked
  provenance: user_confirmed # user_confirmed | agent_authored | source_derived | deferred
  ruling: |
    Candidates are scored on nine weighted criteria, gates block interview.
  applies_to: candidate_judgments, scored_candidates
  detail: |
    Supplied verbatim by the user in the build spec.
```

This block **is** `data/nxd_decisions/nxd_decisions.csv` — the generator writes
the CSV from these rows rather than composing it. See
`nxd-generate-dp`'s `reference/derivation-plan.md` for the column semantics and
the orthogonality of the two axes; nothing here overrides them.

### `## open_questions` (optional)

Gaps you are carrying rather than resolving. Each is either answered by the user
at approval or lands as a `blocked` / `deferred` decision.

```yaml
- id: fx_rates
  question: |
    Which EUR→USD rate, over what date range?
  blocks: [total_opex]
  disposition: blocked       # blocked | deferred | answered
```

A measurement you must not propose (`derivation-plan.md`'s hard boundary) belongs
here, never in `criteria:` or `decisions:` as a value you invented.

## What each section compiles to

| Spec section | Closure artifact |
|---|---|
| `name`, `## intent`, `## questions` | `data_product(...)` name/description; `CONTEXT.md` Intent |
| `## sources` | connector type, `infra-profile.yaml` service, `data/`, the companion path file |
| `## population` | `CONTEXT.md` Population; a `decisions:` row for the sample rule |
| `## models` | `models.py`, `.promise(...)`, `PHYSICAL_MODELS`, the Step-1a plan |
| `## models[].grain` + `.key` | `primary_key()`, the Step-3b Tier-1 uniqueness assert |
| `## gates` | gate columns on the derived model; `UNKNOWN` handling |
| `## criteria` | the landed `scoring_rubric` reference model |
| `## verdicts` | the landed `verdict_thresholds` reference model |
| `## judgments` | `judged_by` / `rubric_version` on the judgement rows; batch cadence |
| `## schedule` | `incremental-transforms.md` route, `transform_state` cursor |
| `## outputs` | `.port("duckdb", …)`, semantic views, static artifact |
| `## decisions` | `data/nxd_decisions/nxd_decisions.csv`, row for row |
| `## open_questions` | `blocked` / `deferred` rows in the same ledger |

Note the direction: **the spec is the source and the closure is the output.** A
value that appears in the closure but in no spec section is a value the user
never approved.

## The validator

```bash
python3 scripts/validate_dp_spec.py path/to/dp-spec.md
```

It is deterministic and finds only what a script can find with certainty. It
does **not** judge whether a rubric is good, whether the questions are the right
questions, or whether a model plan answers them — that stays the read-back's job
and the agent's.

**Errors** (exit 1 — the spec cannot be compiled):

- missing required section or frontmatter key; `status` not one of the three
- a `## criteria` scale with any level between `min` and `max` lacking an anchor
- criteria weights not summing to 1.0 (±0.001)
- `## criteria` present with no `## verdicts`, or a verdict value with neither a
  `min_score` nor a `rule`
- a gate with no `unknown:` handling, or `unknown: FAIL`
- a derived model with no `grain` or no `key`
- a `decisions` row missing `status` or `provenance`, or carrying a value outside
  either vocabulary
- a ruling-bearing section (`criteria`, `verdicts`, `gates`, `population.sample_rule`)
  with no corresponding `decisions` row
- `judgments` present without `rubric_version` in frontmatter
- anything that looks like a credential value in `sources`
- `status: approved` while any error above holds

**Warnings** (exit 0 — compilable, but the read-back must mention it):

- a question no model `answers`
- a model no question motivates
- an `open_questions` entry with `disposition: answered` but no resulting decision
- `incremental: true` alongside a model whose kind implies aggregation or regrain
- an agent-authored value at `status: approved` — legitimate, but it is exactly
  the pair a reviewer should see named

Run it before every read-back and again before invoking the generator. A spec
that fails the validator is not shown to the user as a proposal — fix it first,
or convert the gap into an `open_questions` entry, which is a legitimate answer.

## Approval

The read-back **is** this file. Show it, name what you filled in, and ask for a
correction or approval. The user approves by saying so, or by editing the file
and setting `status: approved`.

- A validator pass is **not** approval. It only means the spec is compilable.
- A technical delivery question answered is **not** approval.
- "Use your judgement" licenses you to author the missing values into the spec
  and show it again. It never licenses moving `status` yourself.

Once approved, the spec is frozen for that build. A later change is an edit plus
a re-approval, and a change to `criteria` is a new `rubric_version`.

## Worked example

A build spec the user wrote in a doc, translated. It validates clean, and
`scripts/validate_dp_spec.py` uses it as its fixture — so an edit here that
breaks the schema is caught by the test, not by a reader.

Note what the translation did to the user's own numbers: the source doc's nine
criteria are carried verbatim, weights and all. Where it gave only the 5 and 1
anchors, the mid-scale anchors are proposed here, marked `agent_authored`, and
carry their own `decisions` row. That is the whole discipline in one example —
nothing of the user's is changed, everything of yours is labelled.

```markdown
---
dp_spec_version: 1
name: candidate_scoring
workflow: candidate-scoring
status: proposed
rubric_version: v1
---

## intent

Given an Ashby job, produce a ranked, gated, auditable list of fraud-cleared
applicants scored against a fixed rubric, so only best-fit candidates reach
interview. Every score traces to a résumé cell the founder can overrule.

## questions

- Who are the top candidates for this job, ranked?
- Which candidates fail a gate, and which gate?
- What evidence supports each candidate's score on each criterion?
- Which candidates could not be scored, and why?

## sources

- type: api
  location: Ashby API — application + candidate + resume
  scope: |
    candidate.fraud_review_status = "Passed Fraud Check" AND job_id = <job_id>.
    The count grows over time; never hardcode it.
  credential_keys: [ashby_api_key]

## population

population: |
  Every application on the parameterized job_id whose candidate passed fraud review.
sample_rule: null
excludes: |
  Nothing. The full filtered population is taken every run.

## models

- name: raw_candidates
  kind: base
  grain: |
    One row per application.
  key: [ashby_candidate_id]
  answers: [q3]
  description: |
    Deterministic extraction. Every cell is a verbatim resume extract or a
    sentinel token. No inference, no judgment, no scores.

- name: scoring_rubric
  kind: reference
  grain: |
    One row per criterion.
  key: [criterion]
  answers: []
  description: |
    The landed rubric: weights, scale bounds and anchors the judgements cite.

- name: candidate_judgments
  kind: base
  grain: |
    One row per candidate x criterion x rubric_version x judged_by.
  key: [entity_key, criterion, rubric_version, judged_by]
  answers: [q3, q4]
  description: |
    Agent-produced scores against the landed rubric, each carrying a verbatim
    evidence citation.

- name: scored_candidates
  kind: derived
  grain: |
    One row per candidate, at the resolved rubric version.
  key: [ashby_candidate_id]
  answers: [q1, q2]
  description: |
    Weighted total, gate results, verdict and rank, joined from the facts,
    judgements and rubric.

## gates

- id: G1
  name: Shipped an agentic system
  rule: |
    Multi-step agents, tool calling, or orchestration — production or a
    substantial public repo. A RAG chatbot alone does not pass, nor do agentic
    terms appearing only in a skills list.
  unknown: UNKNOWN
  blocks: [interview]

- id: G4
  name: Near-term availability
  rule: |
    Available for a 3–4 month contract.
  unknown: UNKNOWN
  blocks: []
  note: |
    Never asked on the form, so this is UNKNOWN for everyone and fails no one.
    It is an outreach question, not a scoring input.

## criteria

- id: C1
  name: Agentic AI depth
  weight: 0.25
  scale: {min: 1, max: 5}
  anchors:
    5: Multi-agent systems or agent infrastructure; handled failure modes; evaluated agent quality.
    4: Shipped a production multi-step agent with tool calling.
    3: Built a substantial agentic side project or prototype.
    2: Integrated an LLM into a product beyond a single call.
    1: Called an LLM API.
  provenance: agent_authored
  evidence_fields: [agentic_llm_frameworks_named, github]
  note: |
    The user supplied 5 and 1; anchors 4, 3 and 2 are proposed here.

- id: C4
  name: Startup and zero-to-one
  weight: 0.25
  scale: {min: 1, max: 5}
  anchors:
    5: Founder or founding engineer; built from nothing to real users.
    4: Early employee on a product that reached real users.
    3: Led a greenfield project inside a larger company.
    2: Some new-product work within an established system.
    1: Career entirely large-enterprise mature systems.
  provenance: agent_authored
  evidence_fields: [startup_zero_to_one_evidence, prior_companies]

- id: C9
  name: Rust
  weight: 0.10
  scale: {min: 1, max: 5}
  anchors:
    5: Ships production Rust.
    4: Rust in professional work.
    3: Rust side projects.
    2: No Rust, but strong adjacent systems work (Go, C, C++, kernel, VM, formal methods).
    1: Neither Rust nor systems-language evidence.
  provenance: user_confirmed
  evidence_fields: [rust_verbatim, other_systems_languages]

- id: C8
  name: CS foundation
  weight: 0.09
  scale: {min: 1, max: 5}
  anchors:
    5: CS/CE degree, or demonstrated fundamentals in systems, compilers, formal methods or performance.
    4: Strong fundamentals evidenced in work, without the formal degree.
    3: Solid engineering background, fundamentals implied rather than shown.
    2: Applied engineering only, no fundamentals signal.
    1: Bootcamp or app-layer only.
  provenance: agent_authored
  evidence_fields: [education, other_systems_languages]

- id: C2
  name: Retrieval and semantic systems
  weight: 0.07
  scale: {min: 1, max: 5}
  anchors:
    5: Production RAG, vector search or semantic models with measured retrieval quality.
    4: Production retrieval work without quality measurement.
    3: Substantial retrieval prototype beyond a template.
    2: Used a retrieval library in a small project.
    1: Used a RAG template.
  provenance: agent_authored
  evidence_fields: [rag_retrieval_vector_named]

- id: C7
  name: Location and timezone
  weight: 0.07
  scale: {min: 1, max: 5}
  anchors:
    5: SF Bay Area or Spain.
    4: US West or Mountain, Portugal, UK, Western Europe, Nordics.
    3: US East or Central, Canada, Eastern Europe, Mexico, MENA.
    2: LatAm, Australia, New Zealand.
    1: Outside every eligible region.
  provenance: user_confirmed
  evidence_fields: [city, country, utc_offset]
  note: |
    Scored against the nearest anchor, SF at UTC-7 or Spain at UTC+2.

- id: C3
  name: Backend and data platform
  weight: 0.06
  scale: {min: 1, max: 5}
  anchors:
    5: Distributed systems, streaming, storage engines — real platform depth.
    4: Substantial backend service work at scale.
    3: Competent backend service and API development.
    2: Backend work mostly framework-level.
    1: App-layer CRUD.
  provenance: agent_authored
  evidence_fields: [python_api_evidence, data_platforms_named]

- id: C5
  name: Judgment and production readiness
  weight: 0.06
  scale: {min: 1, max: 5}
  anchors:
    5: Clear scope and trade-off reasoning; calibrated claims; evident code taste.
    4: Good reasoning with mostly calibrated claims.
    3: Reasonable claims, little visible trade-off reasoning.
    2: Weak calibration or inflated metrics.
    1: No signal, or JD-mirroring — the summary restates the posting and the skills list is every nice-to-have with nothing evidenced.
  provenance: user_confirmed
  evidence_fields: [application_quality_note]
  note: |
    Metric inflation marks C5 down. JD-mirroring scores 1 and is noted
    explicitly — it is the stronger, more disqualifying signal.

- id: C6
  name: Ecosystem adjacency
  weight: 0.05
  scale: {min: 1, max: 5}
  anchors:
    5: MCP, tool registries, data products or mesh, catalogs, governance.
    4: Direct work on one of those areas.
    3: Adjacent exposure through platform or catalog work.
    2: Passing familiarity named without evidence.
    1: None.
  provenance: agent_authored
  evidence_fields: [mcp_data_products_catalogs, governance_named]

## verdicts

values: [interview, interview_if_repo_verifies, different_role, needs_more_info, pass]
bands:
  - verdict: interview
    min_score: 3.8
    rule: |
      Every gate PASS and no unresolved repo dependency.
  - verdict: interview_if_repo_verifies
    min_score: 3.8
    rule: |
      Score reaches the interview band, but the C1/C2/C5 evidence rests on a
      repo that has not been retrieved. A verifiable agentic repo is primary
      evidence and outweighs resume claims.
  - verdict: different_role
    min_score: 3.0
    rule: |
      Strong on C3, C8 or C9 while failing G1 — real engineering depth, wrong
      shape for this contract.
  - verdict: needs_more_info
    min_score: null
    rule: |
      Any gate UNKNOWN, or scored rubric weight below 0.6. This is the only
      verdict an absence-driven cap may resolve to.
  - verdict: pass
    min_score: 0
    rule: |
      Below every band above, with full gate results and no absence cap.
precedence: |
  Gate failure beats score band. An absence-driven cap beats a score band and
  resolves to needs_more_info, never to pass — a cap keyed on absence must name
  the uncertainty rather than deliver a judgement. Among score bands, the
  highest reached wins; interview_if_repo_verifies outranks interview whenever
  the repo dependency is unresolved.

## judgments

- model: candidate_judgments
  produced_by: agent
  generator_model: claude-opus-5
  rubric_version: v1
  prompt_ref: prompts/score_candidate.md
  evidence_required: true
  reruns: incremental

## schedule

trigger: cron
cron: "0 8 * * *"
timezone: America/Los_Angeles
incremental: true
cursor_field: created_at

## outputs

- name: scored_candidates
  kind: semantic_port
  sort: weighted_total desc
  columns: [rank, name, location, weighted_total, gate_results, flags, verdict]

## decisions

- decision_id: candidate_scoring_rubric
  status: confirmed
  provenance: user_confirmed
  ruling: |
    Nine weighted criteria totalling 100%, scored 1-5, with gates that block
    interview without discarding the row.
  applies_to: scoring_rubric, candidate_judgments, scored_candidates
  detail: |
    Supplied verbatim in the user's build spec.

- decision_id: mid_scale_anchors
  status: proposed
  provenance: agent_authored
  ruling: |
    Mid-scale anchors on C1, C4, C8, C2, C3 and C6 were authored here; the
    user's spec gave only the 5 and 1 endpoints for those criteria.
  applies_to: scoring_rubric.anchors
  detail: |
    Interpolated between the two supplied endpoints. Review before trusting any
    mid-scale score. C9, C7 and C5 carry the user's own full scales and are
    recorded separately as user_confirmed.

- decision_id: verdict_bands
  status: proposed
  provenance: agent_authored
  ruling: |
    Five verdicts with score bands and a precedence rule: gate failure beats
    score, an absence cap resolves to needs_more_info and never to pass.
  applies_to: scored_candidates.verdict
  detail: |
    The user's spec named the five verdicts but no thresholds and no
    precedence. Both are proposed here and are the values most likely to move
    on review.

## open_questions

- id: g4_availability
  question: |
    Availability is never collected on the Ashby form. Confirm it stays an
    outreach question rather than a scoring input.
  blocks: []
  disposition: deferred
```
