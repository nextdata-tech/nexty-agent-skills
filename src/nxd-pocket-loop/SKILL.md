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
  version: 0.25.2
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
   → infer the semantic model        (nxd-semantic-data-product)
   → generate the runnable closure    (nxd-generate-dp)
   → build + serve on the supervisor  (nxd-desktop MCP)
   → render the pinned static release  (nxd-dp-static-artifact)
   → describe → translate NL → query → present → refine
```

This skill is the **orchestrator** and the **entry point for any end-to-end
"build me a data product from this source" request** — including one that names
a data product directly. `nxd-generate-dp` constructs the closure once the plan
is settled; it is not where a request starts. If you're in the generator
without having gathered intent, source, questions and any supplied procedure
here first, come back, do Step 1, then invoke the generator from Step 3. It
does not re-teach inference or code generation — it invokes the owning skills,
then drives the supervisor MCP path. Do not expose this routing to the user.

> **You own the conversation and sequencing** — loosely, with **one
> exception**: the policy read-back in Step 1a. Autonomy budgets and
> supervisor-side approval machinery remain deferred, but that gate is enforced
> here, in agent-turn space, since no runtime seam exists to enforce it later.
> Keep one data product in flight at a time while iterating.

## Route the request before doing work

Classify the request before provisioning, generation, or querying, and prefer
the smallest path that gives an honest answer. The full routing table —
deployed-DP / existing-local / no-endpoint / in-scope-source / no-source /
trivial / runtime-unavailable rows — plus step order, remap/regenerate caps,
the one-DP-in-flight rule, and where the loop may fan out to subagents, all
live in [reference/scheduling.md](reference/scheduling.md). The two routes that
decide the whole loop:

- **A source is in scope, no suitable local product exists** → run the loop:
  gather, infer, generate, build, artifact, describe, query, present, refine.
- **An existing local product but no live endpoint/token** (the typical new
session, since the bearer never persists) → **reattach, don't rebuild**:
  `list_data_products` → `resume_data_product` → artifact. `list_data_products`
  is discovery only; it must never supply a static-artifact fallback. See
  [reference/context-and-resume.md](reference/context-and-resume.md).

Treat ambiguous requests conservatively: if a question could mean either a
one-off calculation or analysis of an unseen source, ask which should answer
it. If data is in scope and the user asks for a recurring, shareable, or
multi-question analysis, prefer the reusable local-product path.

## Choose the execution surface

Choose this order before invoking any runtime command:

1. **MCP first.** The `nxd-desktop` server exposes six loop tools —
   `mcp__nxd-desktop__build_data_product`, `mcp__nxd-desktop__resume_data_product`,
   `mcp__nxd-desktop__list_data_products`, `mcp__nxd-desktop__describe_models`,
   `mcp__nxd-desktop__run_semantic_query`, and `mcp__nxd-desktop__inspect_run`
   — use them for the entire discover, build, resume, describe, and query
   sequence, plus a read-only `mcp__nxd-desktop__export_data_product` for
   on-demand handoffs. This is the supported route for Claude Desktop and Claude
   Cowork. Read-only `nxd://` **resources** — with tool bridges where a client
   exposes none — expose what a release *declares*: [reference/catalog-resources.md](reference/catalog-resources.md).
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
definition paths — the connected `nxd-desktop` MCP server runs on the host and
is the runtime authority. The `allowed-tools` frontmatter is restricted by this
plugin's validator to built-in tool names; it cannot enumerate fully qualified
MCP tools. The `mcp__nxd-desktop__…` calls above are nevertheless mandatory
whenever exposed by the session tool registry.

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
- **Any procedure the user already has** — a rubric, gates, weights,
  thresholds, a verdict vocabulary, a selection rule. Ask for it here rather
  than inferring one later: a supplied procedure is the spec, encoded verbatim
  and landed as data, and a gap in it is a question back to the user.
  nxd-generate-dp's `reference/derivation-plan.md` owns how it lands.

Warm the user up before long work: state you'll infer a model, generate the DP,
run it locally, then answer their questions — a multi-minute build is expected,
not a stall. **Determine every source the data product needs before
materializing.** A data product may need one source, or several — the same
connector type twice (two databases), or a mix (a database plus a REST API).
For each source, determine its connector type: local file(s)
(CSV/JSON/JSONL/Parquet), a live database connection, or an off-mesh REST API.
Ask if not already stated; never assume database or API access exists just
because a question sounds analytical. If the request already states a source's
type and details (a host, table names, a base URL), gather everything in one
turn instead of confirming type first and asking a second round — the "ask only
for what's missing" discipline below applies here too, not only the
Pasted-table case.

**The moment there is more than one source, give each a short, distinct label**
(lowercase, hyphenated, e.g. `orders`, `users`) and use it consistently for the
rest of the loop — nxd-generate-dp only *requires* a label to avoid two
same-type sources colliding on one fixed name, but labeling every source once
there are 2+ keeps the build unambiguous. A single-source data product needs no
label; do not invent one. This doesn't conflict with "keep one data product in
flight" above, which limits how many data products you build at once, not how
many sources one may have. Materialize each source faithfully before inference
— repeat the matching bullet once per source when there's more than one,
tagging every artifact with that source's label. **If the request supplied a
procedure (rubric, gates, thresholds, verdicts) with a gap that changes a
result, the policy read-back in Step 3's skill comes FIRST** — reading a source
is always allowed, but copying it into a closure is a materialization and waits
for the user's reply:

- **Attached or workspace source:** make an exact byte-for-byte copy into the
  generated connector export. Do not rewrite delimiter, encoding, headers, or
  rows.
- **Pasted table:** materialize every supplied header and value faithfully in a
  separate CSV export. Do not add columns, coerce values, deduplicate rows, or
  invent an identifier. Treat prose before or after a table as narrative, not a
  data row. A header followed by consistently shaped rows is sufficient
  evidence to proceed: don't claim a value was spliced, truncated, or missing
  merely because the chat renderer visually wraps the prompt. Ask only when the
  table has a real structural ambiguity — a row with a different field count,
  or an unparseable value.
- **Database connection:** record the host/port/database/schema, the
  table(s)/view(s) explicitly named by the user, and the live credentials
  (user/password) supplied now. They land in the generated
  `infra-profile.yaml`'s `db-source` service `attributes` per the credential
  invariant below (shape: `nxd-generate-dp's reference/database-source.md`,
  labeled-instance: `reference/multi-source.md`). Never invent a table name.
- **REST API:** record the base URL, auth scheme, the endpoint(s)/resource(s)
  in scope, a sample response shape if available, any known pagination, and the
  live token/key/credentials if auth is required. They land in the `api-source`
  service `attributes` per the credential invariant below (shape:
  `nxd-generate-dp's reference/api-source.md`, labeled-instance:
  `reference/multi-source.md`). Never fabricate an endpoint.
- **Host path handoff:** pass `build_data_product` only the host-visible,
  absolute output path explicitly returned or exposed by the file-writing tool.
  Never derive a definition path from an opaque attachment ID, a tool-internal
  ID, or a Linux workspace path. If no such path is available, stop and explain
  the local build can't access the materialized definition yet.

> **Fidelity here; derivation downstream.** The rules above govern **source
> materialization only** and are absolute: the CSVs you land are a byte-exact
> record of what the user supplied, so any later number traces back to it.
> Cleaning, dedup, amortization, currency normalization, reclassification and
> regrain are legitimate — often necessary — but exist **only as derived models
> computed downstream of the pristine source**, never as an edit to the source
> export. Preserve the row on the way in, then derive the corrected model beside
> it — nxd-generate-dp owns how.

### Step 2 — Infer the semantic model

Invoke the **nxd-semantic-data-product** skill in its inference mode: profile
each source into `schema.json`, then derive the semantic model — grains,
dimensions, metrics, joins, PII, **and a description on every model, dimension
and metric** (Step 5 reads them to map questions) — from the profile(s) **and**
the user's questions. With 2+ sources profile each separately, carrying labels
forward for Step 3. That skill owns the role grammar.

### Step 3 — Generate the runnable closure

Invoke the **nxd-generate-dp** skill: assemble the complete Python-authored
closure — `spec.py`, `models.py`, `infra-profile.yaml`, `transform/main.py`,
`requirements.txt`, `CONTEXT.md`, and the connector-type-specific artifact(s) —
from the intent, inferred model(s), and connector config. **That skill opens
with a policy read-back gate**: when the request carried a procedure with a gap
that changes a score, verdict, gate outcome, or which rows land, it writes
nothing until the user has seen the enumerated proposal and replied — don't
route around it, and don't treat earlier technical questions as that approval.
Pass through **every** gathered source with its label (or the single unlabeled
source) and its per-model provenance from Step 2, untouched: the file export
plus `csv-source-path`/`file-source-path`, the `db-source-tables` mapping, or
the `api-source-endpoints` mapping — one artifact per source, labeled per
`nxd-generate-dp's reference/multi-source.md` when there's more than one.
**nxd-generate-dp owns the exact per-type (and per-instance) shape — don't
re-derive it here.** That skill owns the local DP shape (DuckDB output port,
dlt-in-transform, local executor), the naming invariant, and the derived models
carrying any business ruling the semantic layer can't express. **Never author
`deployment-spec.yaml`, `manifest.yaml`, or `models.yaml`: the supervisor
compiles those from the Python sources when it pins the definition.** Include
instructions from `reference/dlt.md`. The output is a **closure directory** —
the `--definition` argument for Step 4.

**Steps 2–3 MAY be offloaded to isolated subagents** — a profile subagent and a
separate generate subagent, split at the inference/authoring seam, never one
combined unit — so source reads, codegen, and connector references stay out of
the main conversation. Worth it only when generation would otherwise dominate
the main context. When it does: the policy read-back stays a main-thread user
turn preceding the generate dispatch; the generate subagent hands back a
structured record the main thread builds from without re-reading the closure; and
no live credential enters either subagent (placeholder + host-side injection) —
seam, return contract, credential boundary:
[reference/scheduling.md](reference/scheduling.md).

**Land the closure at a durable, user-visible path — never a temp or scratch
directory.** Put it in a directory named by the workflow id
(`…/nxd-pocket/<workflow>/`), under whichever base the host-visible-path rules
in Step 1 make legal, and **state that path to the user in the handoff**; a
scratch dir is lost when the session ends. The bearer never persists, so a
later session reattaches by **workflow id** (`list_data_products` →
`resume_data_product`) while the **closure path** keys the rebuild fallback
when the published artifact is gone
([reference/context-and-resume.md](reference/context-and-resume.md)) — naming
the dir by the workflow id keeps the two recoverable from each other. The
closure's `CONTEXT.md` (emitted by nxd-generate-dp) is the durable record a
*later* session reads to continue the work — reopen recipe, sample-selection
rule, per-field inference caveats, and the full contract of any
promised-but-unbuilt derived model — and must be self-contained: a derived
model's contract lives inside the closure, never behind a `../` pointer that
the handoff would strand. **Relay the self-check's distribution read-back
before building**, in one or two lines: the value counts printed per
classification column (call out a uniform one), and which assertions are
internal-consistency only rather than checks against the source. A green
self-check means the closure is structurally sound and the transform ran —
never evidence the numbers are right.

### Step 4 — Build and serve through MCP

When the desktop MCP tools are available, call
`mcp__nxd-desktop__build_data_product` with the host-visible absolute closure
path as `definition` and a stable `workflow`; it creates, publishes, and serves
the product for this MCP session. **If a subagent authored the closure (Step
3), verify its returned path resolves on the supervisor's host surface and the
required closure files exist under it before building** — a subagent writes to
its own session surface and cannot itself guarantee the host sees that path
([reference/scheduling.md](reference/scheduling.md)). Treat the returned
`semantic_endpoint` and `bearer_token` as the only connection for later calls;
keep the token out of narration. (Building the same workflow again regenerates
it; **resuming** an already-published workflow — a later session with no live
endpoint — is the fast reattach in
[reference/context-and-resume.md](reference/context-and-resume.md), not a
rebuild.) Fail closed on any build error or missing returned endpoint/token.
Report the MCP build failure and its actionable message; **do not retry through
workspace Bash, SQLite, raw SQL, pandas, or another local database** — a
successful build is the only proof the product is ready to query. The direct
CLI is used only under the confirmed host-local Darwin conditions in "Choose
the execution surface," kept equivalent: same closure served, same
stop-on-failure.

### Step 4a — Render the pinned static artifact

After every successful build or resume, invoke **nxd-dp-static-artifact** for
the workflow before `describe_models` or any query. It reads only the current,
verified, and outputs documents (by resource operations, or the bridge tools on a
client exposing none) and writes one self-contained release HTML
file. Report artifact `status`, `path`, and `publish_seq` separately from the
endpoint. If it fails, report that failure but keep a healthy endpoint usable
for the later describe/query path. An endpoint plus bearer but **no workflow**
is the explicit query-only exception: state that the artifact is unavailable,
then describe/query without inventing a workflow; a query remap does not rerender.
A same-workflow rebuild discards cached URIs and the former current
file, then renders its new sequence before describe/query.

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
   `filters[]` (`=`, `!=`, `<>`, `>`, `>=`, `<`, `<=`, `LIKE`, `ILIKE`; ANDed
   only; values are strings), `order_by[]` (names must be among the selected
   measures/dimensions) and `limit` (capped at 200 rows) — **not**
   `IN`/`BETWEEN`/`IS NULL`/`NOT LIKE`, `HAVING` or measure-level filtering,
   `OR`, raw-row retrieval, or raw SQL. Apply the **Omission Test** to every
   constraint before placing it — see
   [reference/query-grammar.md](reference/query-grammar.md). Would a consumer
   who never heard the constraint, querying with no filters, get a **wrong**
   number (a **standing ruling** → materialize it in a derived model, Step 6)
   or merely a **broader** one (a **per-question constraint** → express it with
   `filters[]`/`order_by[]`/`limit` here)? When ambiguous, ask; with no user,
   materialize. If a genuine per-question constraint outruns the grammar, use
   the sanctioned patterns in that reference (group-and-read, two ANDed filters
   for a range, `order_by`+`limit` for a threshold) — never re-aggregate
   agent-side, and never silently drop the constraint.
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

- **Query-level** (cheapest) — the model is right but the selection was wrong
  or a dimension was missing. Re-describe, re-map, then re-query through MCP.
- **Model / DP-level** — the inferred model is wrong (missing metric, wrong
  grain, missing join, wrong PII, or an undistinguishing description), or the
  question needs a column or grain that doesn't exist (a filtered figure, a
  ratio, a monthly rollup, a classification) — a **derived model**, not a
  query tweak: go
  back to Step 2/3 and have nxd-generate-dp materialize the ruling, then
  rebuild through MCP with the **same** `workflow`. **After every rebuild,
  refresh:** discard cached artifact resources and current file; render the new
  release first, then use the endpoint/token returned by the build and describe
  the catalog before mapping again. Define success as a catalog-grounded answer the user
  accepts. If the loop doesn't converge within the caps, report what you tried,
  what the product currently declares, and where the gap is — never loop
  indefinitely or give up silently.

## When questions require inference

Some questions need a **judgement produced by reading each entity's evidence**
— a per-entity score, verdict, or classification. It is nondeterministic, so
route it like any ruling: **land it as data, produced agent-side, before the
build**, teaching the rubric as data FIRST. `reference/inference.md` owns *when
the agent judges* (teach/judge/incremental, unscored-bucket degrade); the row
schema is nxd-generate-dp's `reference/llm-judgments.md`.

## Narration discipline (always)

- **Warm up** before any multi-minute step (inference, generation, serve), and
  report entering each phase — never a silent stall.
- **Label previews as previews.** A sampled, partial, or `truncated` result is
  a preview, not a verified answer — say so, and never present an unvalidated
  intermediate as the final answer.
- **Show the query behind the answer** — every answer states the
  measure/dimension selection that produced it, and the ruling behind any
  dimension whose catalog description names one.
- **Disclose proposed judgement, and quantify the unscored bucket.** An answer
  resting on a model an agent judgement `applies_to` says so ("built on
  proposed agent judgements, rubric v1"), never as confirmed fact, and reports
  the unscored share like a `needs_review` share — a score over a
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
  `infra-profile.yaml` connector service's `attributes` — never elsewhere,
  never in chat. Who writes it: nxd-generate-dp inline, or the orchestrator
  host-side after hand-back when offloaded (the subagent wrote only a
  placeholder — see the subagent invariant below); this differs from the
  bearer-token invariant below, never written to any file. Once landed, **the
  closure directory itself is sensitive** — don't commit, zip, attach it, or
  reuse it as a template without first clearing the old credential; to *share*
  it, use `export_data_product`, never a hand-zip (invariant below).
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
- **Land judgement as data, never code.** Confirm mappings and agent-produced
  scores/verdicts, keep their evidence/status, and materialize them as models.
- **A supplied procedure with a result-changing gap is read back BEFORE any
  materialization.** No closure directory, source copy, generated code, table,
  scoring, or build until the user has seen every proposed anchor, band and
  precedence rule and replied. A technical delivery question is not approval;
  "use your judgement" licenses authoring the proposal, not skipping the turn.
- **A ruling behind a number is stated with the number.** When a dimension's
  catalog description names the ruling that created it, the answer says so, and
  a classified total reports its review-bucket share whenever nonzero —
  silently resting on an unstated ruling is the failure this loop prevents.
- **Keep governed analysis on the supervisor path.** Never answer a governed
  local-data question with SQLite, `sqlite3`, raw SQL, pandas aggregation, or a
  shell pipeline as fallback — the supervisor may compile semantic selections
  internally, but never author or execute raw SQL to bypass it.
- **MCP is authoritative when connected.** If `nxd-desktop` MCP tools are
  present, discover, build, resume, describe, and query through them. A failed
  MCP build is a reported failure, not permission to use a workspace-shell or
  database fallback.
- **Reattach, don't rebuild, when the artifact is live.** In a fresh session
  with no endpoint, `list_data_products` → `resume_data_product` → static
  artifact recovers a published workflow in seconds with a fresh bearer;
  `list_data_products` remains discovery only; rebuild only when
  `collected` / `artifact_unavailable`
  ([reference/context-and-resume.md](reference/context-and-resume.md)).
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
- **Query is by measure/dimension name, not raw SQL or NL.** Ground the
  NL→selection translation in `describe_models`. The desktop MCP query contract
  accepts measures, dimensions, ANDed `filters[]`, `order_by[]` and `limit` for
  **per-question scoping only** — never emulate its gaps by re-aggregating
  agent-side.
- **A standing ruling materializes; a filter never enforces one.** Apply the
  **Omission Test** ([reference/query-grammar.md](reference/query-grammar.md)):
  if no-filter querying would get a *wrong* number, the ruling belongs in the
  transform, and the ruling-bearing measure must be correct unfiltered. Landing
  an `is_transfer` dimension and expecting callers to filter on it is the same
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

Use [scheduling](reference/scheduling.md), [context-and-resume](reference/context-and-resume.md),
[inference](reference/inference.md), [handoff-export](reference/handoff-export.md),
[query grammar](reference/query-grammar.md), and [dlt](reference/dlt.md) for their named details.
