---
name: nxd-pocket-loop
description: THE ENTRY POINT for local business-data work — whether the user asks a question or asks to BUILD. Use when a task references tabular business data (CSVs, spreadsheets, exports, a live database, a REST API) and the user wants an analytical answer they may revisit (breakdown, ranking, comparison, trend, anomaly, driver) OR asks to build or generate a data product over it. A direct build request — "build me a data product", "score these against my rubric" — starts HERE, not in nxd-generate-dp: this skill gathers intent, source, questions and any supplied procedure (rubric, gates, weights, thresholds, verdicts), runs the mandatory policy read-back when that procedure has gaps, then invokes nxd-generate-dp. Going straight to the generator skips the co-authoring checkpoint and encodes a policy the user never saw. Answer only from the product's semantic query result; never substitute raw SQL, pandas, or shell aggregation. Not for one-off arithmetic. For a deployed platform product, use nxd-data-product-query.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
# The plugin validator permits only built-in Claude Code tool names here.
# nxd-desktop MCP capabilities are selected by their fully qualified names below.
metadata:
  author: nextdata
  version: 0.27.0
---

# nxd-pocket-loop skill

## Overview

This skill is the analyst-facing entry point for local business-data questions.
Start from the user's outcome and available data, not internal product
language. When a durable local product is useful, drive the **Nexty Pocket
loop**: a natural-language intent plus a local data source become a running,
queryable data product on a local desktop supervisor — no Kubernetes, no remote
warehouse. The loop is:

```
intent + source + questions
   → author dp-spec.md, the IR        (user-editable; the policy read-back)
   → infer the semantic model        (nxd-semantic-data-product)
   → generate the runnable closure    (nxd-generate-dp)
   → build + serve on the supervisor  (nxd-desktop MCP)
   → render the pinned static release  (nxd-dp-static-artifact)
   → describe → translate NL → query → present → refine
```

This skill is the **orchestrator** and the **entry point for any end-to-end
"build me a data product from this source" request**. `nxd-generate-dp`
constructs the closure once the plan is settled; it is not where a request
starts — if you are in the generator without having done Steps 1–1b here, come
back, do them, then invoke it from Step 3. This skill does not re-teach inference
or code generation; it invokes the owning skills, then drives the supervisor MCP
path. Do not expose this routing to the user.

> **You own the conversation and sequencing** — loosely, with **one exception**:
> the policy read-back, discharged by the approved `dp-spec.md` in Step 1b. That
> gate is enforced here, in agent-turn space, since no runtime seam exists to
> enforce it later. Keep one data product in flight at a time while iterating.

## Route the request before doing work

Classify the request before provisioning, generation, or querying, and prefer
the smallest path that gives an honest answer. The full routing table plus step
order, remap/regenerate caps, the one-DP-in-flight rule and the subagent fan-out
live in [reference/scheduling.md](reference/scheduling.md). The two routes that
decide the whole loop:

- **A source is in scope, no suitable local product exists** → run the loop:
  gather, spec, infer, generate, build, artifact, describe, query, present,
  refine.
- **An existing local product but no live endpoint/token** (the typical new
  session, since the bearer never persists) → **reattach, don't rebuild**:
  `list_data_products` → `resume_data_product` → artifact. `list_data_products` is
  discovery only and must never supply a static-artifact fallback — see
  [reference/context-and-resume.md](reference/context-and-resume.md).

Treat ambiguous requests conservatively: if a question could mean either a
one-off calculation or analysis of an unseen source, ask which should answer it.
Prefer the reusable local-product path for a recurring, shareable, or
multi-question analysis.

## Choose the execution surface

Choose this order before invoking any runtime command:

1. **MCP first.** The `nxd-desktop` server exposes six loop tools —
   `mcp__nxd-desktop__build_data_product`, `mcp__nxd-desktop__resume_data_product`,
   `mcp__nxd-desktop__list_data_products`, `mcp__nxd-desktop__describe_models`,
   `mcp__nxd-desktop__run_semantic_query`, and `mcp__nxd-desktop__inspect_run`
   — use them for the entire discover, build, resume, describe, and query
   sequence, plus a read-only `mcp__nxd-desktop__export_data_product` for
   on-demand handoffs. This is the supported route for Claude Desktop and Claude
   Cowork. Read-only `nxd://` **resources** — with tool bridges where a client exposes none —
   expose what a release *declares*: [reference/catalog-resources.md](reference/catalog-resources.md).
2. **Direct CLI only on a confirmed host-local Darwin shell.** Use
   `nxd-desktop-supervisor` only when the session context has positively
   established that the shell is the user's macOS host **and** both
   `nxd-desktop-supervisor` and its sibling `nxd-desktop-kernel-host` are
   present together. If either fact isn't already established, don't assume it
   from a path, home directory, or prior task.
3. **Otherwise stop.** Report that no usable local desktop runtime is connected
   and give the provisioning/connection recovery action.

In Claude Cowork, its workspace `Bash` is an isolated Linux environment. Use it
only to read, stage, or materialize task files. **Never run `uname`, binary
probes, or supervisor commands there**, and never use its Linux paths as MCP
definition paths — the connected `nxd-desktop` MCP server runs on the host and is
the runtime authority. The `allowed-tools` frontmatter is restricted by this
plugin's validator to built-in tool names and cannot enumerate fully qualified
MCP tools; the `mcp__nxd-desktop__…` calls above are nevertheless mandatory
whenever the session tool registry exposes them.

## The loop — step by step

### Step 1 — Gather intent, source, and questions

Establish three things (ask the user for whatever is missing):

- **Intent** — what the data product is about, in the user's words.
- **Source** — where the in-scope local data lives. Preserve it exactly; if it
  is not already a connector export, keep any generated export copy separate
  from the supplied source.
- **Questions** — the natural-language questions the DP must answer. These
  drive the whole inference (right-to-left): the model is judged by whether it
  answers them.
- **Any procedure the user already has** — a rubric, gates, weights, thresholds,
  a verdict vocabulary, a selection rule. Ask for it here rather than inferring
  one later: a supplied procedure is the spec, encoded verbatim and landed as
  data, and a gap in it is a question back to the user (nxd-generate-dp's
  `reference/derivation-plan.md` owns how it lands). **If the user already wrote
  it down** — a build spec, a requirements doc, a rubric page — take the doc
  rather than asking them to re-state it; Step 1b translates it.

Warm the user up before long work: state you'll write the spec, generate the DP,
run it locally, then answer their questions — a multi-minute build is expected,
not a stall. **Determine every source the data product needs before
materializing.** A data product may need one source or several — the same
connector type twice (two databases), or a mix (a database plus a REST API). For
each, determine its connector type: local file(s) (CSV/JSON/JSONL/Parquet), a
live database connection, or an off-mesh REST API. Ask if not already stated;
never assume database or API access exists just because a question sounds
analytical. If the request already states a source's type and details, gather
everything in one turn rather than confirming type first and asking a second
round.

**The moment there is more than one source, give each a short, distinct label**
(lowercase, hyphenated, e.g. `orders`, `users`) and use it consistently for the
rest of the loop; a single-source data product needs none, so don't invent one.
This doesn't conflict with "keep one data product in flight" above, which limits
how many data products you build at once, not how many sources one may have.
Materialize each source faithfully before inference — repeat the matching bullet
once per source, tagging every artifact with that source's label. **If the request supplied a
procedure (rubric, gates, thresholds, verdicts) with a gap that changes a
result, the policy read-back in Step 3's skill comes FIRST** — reading a source
is always allowed, but copying it into a closure is a materialization and waits
for the user's reply:

Per-kind rules — attached file, pasted table, database, REST API, and the
host-path handoff — plus where credentials land are in
[reference/source-materialization.md](reference/source-materialization.md).

> **Fidelity here; derivation downstream.** Those rules govern **source
> materialization only** and are absolute: the rows you land are a byte-exact
> record of what the user supplied, so any later number traces back to it.
> Cleaning, dedup, amortization, currency normalization, reclassification and
> regrain are legitimate — often necessary — but exist **only as derived models
> computed downstream of the pristine source**, never as an edit to the source
> export.

### Step 1b — Author `dp-spec.md`, the intermediate representation

Write what Step 1 gathered into **`dp-spec.md`** at
`…/nxd-pocket/<workflow>/dp-spec.md`, beside the closure (which lands at
`closure/`) — the user-editable IR carrying intent, questions, sources,
population, the model plan, any gates / criteria / verdicts / judgements /
schedule, the rulings ledger, and every open question. Schema, authoring modes
and the compile map: [reference/dp-spec.md](reference/dp-spec.md).

It is **not a closure file**, so writing it is not a materialization and the
policy gate is not violated by it. Nothing under `closure/` is written until the
user replies.

**If the user supplied a doc** — a build spec, a rubric page — translate it onto
the schema rather than asking them to re-type it. Their values are the
specification: encode them verbatim, add what is missing marked `provenance:
agent_authored`, and **show what you filled in**. Never change a value they wrote,
never silently fix weights that do not sum, never mark your own addition
`user_confirmed`. Draft the whole file when they only described it; edit and
re-approve an existing one on a later pass.

Then **validate** — `python3 scripts/validate_dp_spec.py <path>/dp-spec.md` —
which deterministically finds the gap classes the gate fires on: a scale defining
only its endpoints, weights that do not sum, a verdict no band reaches, a gate
with no `UNKNOWN` rule, a ruling with no ledger row, a judgement with no
`generator_model`. Fix each, or carry it as an `open_questions` entry, before
showing the spec.

**This file is the policy read-back.** When the request carried a procedure with
a result-changing gap, show the spec, name every value you authored, and wait —
the gate in Step 3's skill is discharged by the user's reply to *this*. **A
validator pass is not approval**, and `status: approved` is the user's to set.
With no procedure in play the spec is still written (it is the generator's input)
but needs no approval turn.

**When a question needs a judgement read from each entity's evidence** — a
per-entity score, verdict or classification — it is nondeterministic, so route it
like any ruling: **land it as data, produced agent-side, before the build**, with
the rubric taught as data FIRST. Declare it in the spec's `judgments:` block,
naming the `generator_model` that will produce the rows.
[reference/inference.md](reference/inference.md) owns *when the agent judges*;
the row schema is nxd-generate-dp's `reference/llm-judgments.md`.

### Step 2 — Infer the semantic model

Invoke the **nxd-semantic-data-product** skill in its inference mode: profile
each source into `schema.json`, then derive the semantic model — grains,
dimensions, metrics, joins, PII, **and a description on every model, dimension
and metric** (Step 5 reads them to map questions) — from the profile(s), the
user's questions, and the spec's `models:` plan. With 2+ sources profile each
separately, carrying labels forward. That skill owns the role grammar.

### Step 3 — Generate the runnable closure

Invoke the **nxd-generate-dp** skill: assemble the complete Python-authored
closure — `spec.py`, `models.py`, `infra-profile.yaml`, `transform/main.py`,
`requirements.txt`, `CONTEXT.md`, and the connector-type-specific artifact(s) —
from the **approved `dp-spec.md`** (Step 1b), the inferred model(s), and the
connector config. Pass the spec's path: it carries the intent, questions, model
plan and every ruling, so the generator compiles rather than re-derives, and the
`decisions:` block becomes `nxd_decisions` row for row. **That skill opens with a
policy read-back gate**: when the request carried a procedure with a gap that
changes a score, verdict, gate outcome, or which rows land, it writes nothing
until the user has seen the enumerated proposal and replied — the approved spec
is what discharges it, so don't route around it, and don't treat earlier
technical questions as that approval.
Pass through **every** gathered source with its label (or the single unlabeled
source) and its per-model provenance from Step 2, untouched — one artifact per
source, labeled per `nxd-generate-dp's reference/multi-source.md` when there's
more than one. **That skill owns the exact per-type shape — don't re-derive it
here**, along with the local DP shape (DuckDB output port, dlt-in-transform,
local executor), the naming invariant, and the derived models carrying any
business ruling the semantic layer can't express. **Never author
`deployment-spec.yaml`, `manifest.yaml`, or `models.yaml`: the supervisor
compiles those from the Python sources when it pins the definition.** Include
instructions from `reference/dlt.md`. The output is a **closure directory** —
the `--definition` argument for Step 4.

**Steps 2–3 MAY be offloaded to isolated subagents** — a profile subagent and a
separate generate subagent, split at the inference/authoring seam, never one
combined unit — but only when generation would otherwise dominate the main
context. The policy read-back stays a main-thread user turn preceding the
dispatch, and no live credential enters either subagent. Seam, return contract
and credential boundary: [reference/scheduling.md](reference/scheduling.md).

**Land the closure at a durable, user-visible path — never a temp or scratch
directory.** Put it under a directory named by the workflow id, with the IR
beside it: `…/nxd-pocket/<workflow>/dp-spec.md` and
`…/nxd-pocket/<workflow>/closure/` — the latter is what `build_data_product`
receives. Use whichever base the host-visible-path rules in Step 1 make legal,
and **state both paths to the user in the handoff**; a scratch dir is lost when
the session ends. The bearer never persists, so a later session reattaches by
**workflow id** (`list_data_products` → `resume_data_product`) while the
**closure path** keys the rebuild fallback when the published artifact is gone
([reference/context-and-resume.md](reference/context-and-resume.md)) — naming
the dir by the workflow id keeps the two recoverable from each other. The
closure's `CONTEXT.md` (emitted by nxd-generate-dp) is the durable record a
*later* session reads to continue the work, and must be **self-contained**: a
derived model's contract lives inside the closure, never behind a `../` pointer
the handoff would strand — `../dp-spec.md` included, since the IR is upstream of
the closure, not a dependency of it. **Relay the self-check's distribution
read-back before building**, in one or two lines: the per-classification-column
value counts (call out a uniform one), and which assertions are
internal-consistency only rather than checks against the source. A green
self-check means the closure is structurally sound and the transform ran — never
evidence the numbers are right.

### Step 4 — Build and serve through MCP

When the desktop MCP tools are available, call
`mcp__nxd-desktop__build_data_product` with the host-visible absolute path of the
`closure/` directory as `definition` and a stable `workflow`; it creates,
publishes, and serves the product for this MCP session. **If a subagent authored
the closure (Step 3), verify its returned path resolves on the supervisor's host
surface and the required closure files exist under it before building** — a
subagent writes to its own session surface and cannot guarantee the host sees
that path ([reference/scheduling.md](reference/scheduling.md)). Treat the
returned `semantic_endpoint` and `bearer_token` as the only connection for later
calls; keep the token out of narration. (Building the same workflow again
regenerates it; **resuming** an already-published workflow is the fast reattach
in [reference/context-and-resume.md](reference/context-and-resume.md), not a
rebuild.) Fail closed on any build error or missing endpoint/token: report the
failure and its actionable message, and **do not retry through workspace Bash,
SQLite, raw SQL, pandas, or another local database** — a successful build is the
only proof the product is ready to query. The direct CLI is used only under the
confirmed host-local Darwin conditions in "Choose the execution surface," kept
equivalent: same closure served, same stop-on-failure.

### Step 4a — Render the pinned static artifact

After every successful build or resume, invoke **nxd-dp-static-artifact** for the
workflow before `describe_models` or any query. It reads only the current,
verified and outputs documents and writes one self-contained release HTML file.
Report artifact `status`, `path` and `publish_seq` separately from the endpoint;
on failure report it but keep a healthy endpoint usable for describe/query. With
an endpoint but **no workflow**, say the artifact is unavailable and query on. A
rebuild discards cached URIs and renders its new sequence.

### Step 5 — Describe, query, and present

The query surface is **structured** (measure/dimension names); the
natural-language translation is yours to do. For each question:

1. **Describe the served catalog first.** Call `mcp__nxd-desktop__describe_models`
   with the endpoint/token returned by the build (or supplied for an existing
   local product) — the declared vocabulary is canonical, don't guess concept
   names from source columns.
2. **Map the NL question to a selection.** Pick the measure(s)/dimension(s)
   that answer it — reuse the question→concept mapping approach from
   **nxd-data-product-query**'s semantic-layer section. Before running, restate
   the selection chosen and, if ambiguous against the declared concepts, ask
   rather than silently picking.
3. **Check the question fits the MCP grammar.**
   `mcp__nxd-desktop__run_semantic_query` accepts `measures[]`, `dimensions[]`,
   ANDed `filters[]`, `order_by[]` and `limit` — no `OR`, no measure-level
   filtering, no raw rows, no SQL. The full operator list, the sanctioned
   workarounds (group-and-read, two ANDed filters for a range, `order_by`+`limit`
   for a threshold) and the **Omission Test** are in
   [reference/query-grammar.md](reference/query-grammar.md). Apply that test to
   every constraint first: would a consumer querying with no filters get a
   **wrong** number (a **standing ruling** → materialize it, Step 6) or merely a
   **broader** one (a **per-question constraint** → express it here)? When
   ambiguous, ask; with no user, materialize. Never re-aggregate agent-side, and
   never silently drop the constraint.
4. **Run the governed query.** Call `mcp__nxd-desktop__run_semantic_query` with
   the endpoint/token plus the selected measures/dimensions — don't bypass it
   with raw SQL or a local aggregation.
5. **Quantify the review bucket before presenting a classified total.** If the
   selection's model carries a classification dimension with a review bucket
   (`needs_review`, `unmapped`, `other`), a single headline number hides how
   much is unclassified. Run the same measure grouped by that dimension and
   report the bucket's share alongside the total whenever nonzero — "€480k
   total; €190k (40%) is `needs_review`". A classified total with an
   unquantified review bucket is a preview, not an answer.
6. **Parse + present.** Render the returned rows as a compact table and state
   the semantic selection that produced them. Surface any ruling behind the
   answer: if a dimension grouped by or filtered on carries a `describe_models`
   description naming a ruling (a mapping, an exclusion, a reclassification),
   state it in the answer — the consumer trusts it whether or not they know it
   exists. Label any partial or unverified result as a preview, not the
   complete answer.

### Step 6 — Refine wrong answers back into the loop

If an answer is wrong, missing, or unsatisfying, decide where the fix belongs.
Both levels are **bounded** — caps (remap ≤~2/question, regenerate ≤~3 total)
and the non-convergence report live in
[reference/scheduling.md](reference/scheduling.md):

- **Query-level** (cheapest) — the model is right but the selection was wrong or
  a dimension was missing. Re-describe, re-map, re-query through MCP.
- **Model / DP-level** — the inferred model is wrong (missing metric, wrong
  grain, missing join, wrong PII, an undistinguishing description), or the
  question needs a column or grain that doesn't exist (a filtered figure, a
  ratio, a monthly rollup, a classification) — a **derived model**, not a tweak. **Edit `dp-spec.md` first**, re-validate, and re-approve it when the
  change touches a ruling (a criteria change is a new `rubric_version`); then go
  back to Step 2/3 and rebuild through MCP with the **same** `workflow`. **After
  every rebuild, refresh:** discard cached artifact resources and current file;
  render the new release first, then describe the catalog with the returned
  endpoint/token before mapping again. Success is a catalog-grounded answer the
  user accepts. If the loop doesn't converge within the caps, report what you
  tried, what the product declares, and where the gap is — never loop
  indefinitely or give up silently.

## Narration discipline (always)

- **Warm up** before any multi-minute step (inference, generation, serve), and
  report entering each phase — never a silent stall.
- **Label previews as previews.** A sampled, partial, or `truncated` result is a
  preview, not a verified answer — say so, and never present an unvalidated
  intermediate as final.
- **Show the query behind the answer, and the ruling behind the query** — every
  answer states the measure/dimension selection that produced it, plus the ruling
  behind any dimension whose catalog description names one.
- **Disclose proposed judgement, and quantify the unscored bucket.** An answer
  resting on a model an agent judgement `applies_to` says so ("built on proposed
  agent judgements, rubric v1"), never as confirmed fact, and reports the
  unscored share like a `needs_review` share — a score over a
  silently-incomplete population is a preview, not an answer.

## Invariants — never violate these

- **Do not re-teach inference or code generation** — invoke
  nxd-semantic-data-product and nxd-generate-dp.
- **Preserve supplied data.** Never modify an input file, its headers, or its
  rows; never add an identifier or fabricate a key. A generated file-connector
  export may contain only an exact copy kept separate from the source — this
  governs **source materialization**, no exception. For a live database or REST
  API source, treat access as **read-only**: never write to it, never fabricate
  a table/endpoint the user didn't name, never invent or narrate a raw
  credential. A real credential lands in exactly one place — the generated
  `infra-profile.yaml` connector service's `attributes` — never elsewhere, never
  in chat, and never in `dp-spec.md`, which names key names only. It is written
  by nxd-generate-dp inline, or host-side by the orchestrator after hand-back
  when offloaded (the subagent wrote only a placeholder). Once landed, **the
  closure directory itself is sensitive** — don't commit, zip, attach, or reuse
  it as a template without first clearing the old credential; to *share* it, use
  `export_data_product`, never a hand-zip (invariant below).
- **Label every source once there are 2+.** A single-source data product needs
  no label. With multiple sources, each gets a short, distinct label used
  consistently across materialization, inference, and generation; never let two
  sources of the same connector type share an unlabeled or duplicate name —
  that's a collision nxd-generate-dp can't resolve for you.
- **Correct data downstream, never upstream.** Cleaning, deduplication,
  amortization, currency normalization, reclassification and regrain belong in
  **derived models computed from the pristine source** — authored by
  nxd-generate-dp, landed through the DuckDB output port, asserted in the
  transform. Never edit the source export to reach that outcome, and never
  emulate it agent-side.
- **A judgement not in the data is confirmed and landed, not hardcoded.** FX
  rates, merchant→category and similar mappings are surfaced, confirmed, and
  landed as their own queryable model — never embedded as transform constants.
  **This covers agent-produced judgement too** — a per-entity
  score/verdict/classification read from evidence, landed agent-side as data
  (`status = proposed`, evidence-cited, rubric taught first); the build never
  invokes a model, and a per-entity judgement baked in as a constant is
  hardcoded even when weighted.
- **A supplied procedure with a result-changing gap is read back BEFORE any
  materialization.** No closure directory, source copy, generated code, table,
  scoring, or build until the user has seen every proposed anchor, band and
  precedence rule and replied. A technical delivery question is not approval;
  "use your judgement" licenses authoring the proposal, not skipping the turn.
- **The plan is a file before it is code.** Every build is preceded by a
  `dp-spec.md` (Step 1b) written beside the closure, never inside it, and passed
  to the generator. A user-supplied value in it is encoded verbatim; a value you
  authored is marked `agent_authored` and named in the read-back; `status:
  approved` is the user's to set, never yours. Run
  `scripts/validate_dp_spec.py` before the read-back and again before generating
  — but a validator pass only means compilable, never approved.
- **A ruling behind a number is stated with the number.** When a dimension's
  catalog description names the ruling that created it, the answer says so, and
  a classified total reports its review-bucket share whenever nonzero —
  silently resting on an unstated ruling is the failure this loop prevents.
- **Keep governed analysis on the supervisor path, and MCP is authoritative when
  connected.** Discover, build, resume, describe and query through the
  `nxd-desktop` tools whenever present. Never answer a governed local-data
  question with SQLite, raw SQL, pandas, or a shell pipeline as fallback, and
  never author raw SQL to bypass the semantic layer — a failed MCP build is a
  reported failure, not permission to route around it.
- **Reattach, don't rebuild, when the artifact is live.** In a fresh session
  with no endpoint, `list_data_products` → `resume_data_product` → static
  artifact recovers a published workflow in seconds with a fresh bearer;
  `list_data_products` remains discovery only; rebuild only when `collected` /
  `artifact_unavailable` ([reference/context-and-resume.md](reference/context-and-resume.md)).
- **Hand off only host-visible paths.** Pass `build_data_product` an absolute
  generated-definition path explicitly exposed by the file-writing surface;
  never infer one from an attachment ID or isolated Linux path, and verify a
  generation subagent's returned path host-side before build.
- **A subagent never owns the policy turn and never holds a credential.** When
  generation is offloaded (Step 3), the policy read-back stays a main-thread
  user turn — a subagent returns `gap_found` on a new gap instead of opening
  one; and a live credential is placeholdered in the subagent, injected
  host-side before build, never in its prompt, return, or narration
  ([reference/scheduling.md](reference/scheduling.md)).
- **Query is by measure/dimension name, and a standing ruling materializes — a
  filter never enforces one.** Ground the NL→selection translation in
  `describe_models`; the MCP contract's measures, dimensions, ANDed `filters[]`,
  `order_by[]` and `limit` are for **per-question scoping only**, never emulated
  by re-aggregating agent-side. Apply the **Omission Test**
  ([reference/query-grammar.md](reference/query-grammar.md)): if no-filter
  querying would get a *wrong* number, the ruling belongs in the transform and
  the ruling-bearing measure must be correct unfiltered. Landing an
  `is_transfer` dimension and expecting callers to filter on it is the same
  silent failure wearing a column — only a constraint that merely makes the
  answer *broader* is a query-time filter.
- **One workflow id per data product.** Rebuild the same id to regenerate;
  resume it to reattach — a different id is a different product and replaces
  the current endpoint.
- **The supervisor data dir is off-limits.** Everything under `.pocket/state/`
  — pinned snapshots in `definitions/<id>/`, `state.sqlite*`, `staging/` — is
  immutable supervisor-owned state; never `chmod`, edit, or hand-write it. A
  `.../staging/run-<id>/data.duckdb` path inside a pinned `manifest.yaml` is the
  supervisor's own resolved runtime path, not a defect. If a served closure is
  wrong, fix **your** source dir and re-`serve` — the supervisor re-pins.
- **Share only via `export_data_product`.** Never hand-zip a credential-bearing closure —
  its fail-closed redaction is the credential boundary ([reference/handoff-export.md](reference/handoff-export.md)).
- **Bearer only as a tool parameter** — keep it out of narration, never persist
  or print it. **Never present a preview or truncated result as verified data**,
  and never stall silently. **The loop is bounded** — cap query remaps and
  regenerate cycles; report non-convergence ([reference/scheduling.md](reference/scheduling.md)).

## Reference skills

| Skill | Role in the loop |
|-------|------------------|
| `nxd-semantic-data-product` | Infers the semantic model from the source + questions (Step 2) |
| `nxd-generate-dp` | Generates the runnable local closure the supervisor serves (Step 3), including local-file, database, and REST API connector config — see its own `reference/` for the connector-type-specific shape, and `reference/llm-judgments.md` for landing an agent judgement (score/verdict/classification) as data. |
| `nxd-dp-static-artifact` | Renders the pinned release HTML after build/resume and before describe/query (Step 4a) |
| `nxd-data-product-query` | Source of the question→concept mapping approach (Step 5) |

## Reference docs (this skill)

Use [dp-spec](reference/dp-spec.md),
[source-materialization](reference/source-materialization.md),
[scheduling](reference/scheduling.md),
[context-and-resume](reference/context-and-resume.md),
[inference](reference/inference.md), [handoff-export](reference/handoff-export.md),
[query grammar](reference/query-grammar.md), and [dlt](reference/dlt.md) for their named details.
