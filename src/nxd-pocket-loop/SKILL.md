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
  version: 0.16.0
---

# nxd-pocket-loop skill

## Overview

This skill is the analyst-facing entry point for local business-data questions.
Start from the user's outcome and available data, not internal product language.
When a durable local product is useful, drive the **Nexty Pocket loop**: a
natural-language intent plus a local data source become a running, queryable
data product on a local desktop supervisor — no Kubernetes, no remote
warehouse. The loop is:

```
intent + source + questions
   → infer the semantic model        (nxd-semantic-data-product)
   → generate the runnable closure    (nxd-generate-dp)
   → build + serve on the supervisor  (nxd-desktop MCP)
   → translate NL question → query    (this skill, agent-side)
   → answer, and refine wrong answers back into a regenerate
```

This skill is the **orchestrator**, and it is the **entry point for any
end-to-end "build me a data product from this source" request** — including one
that names a data product directly. `nxd-generate-dp` is the specialist that
constructs the closure once the plan is settled; it is not the place a request
starts. If you find yourself in the generator without having gathered the
intent, source, questions and any supplied procedure here first, you skipped a
step: come back, do Step 1, and invoke the generator from Step 3. It does not
re-teach inference or code generation — it invokes the skills that own those,
then drives the supervisor MCP path. Do not expose this routing to the user.

> **You own the conversation and the sequencing.** This skill narrates progress
> and sequences the work loosely — with **one exception that is not loose**: the
> policy read-back in Step 1a. Autonomy budgets and supervisor-side approval
> machinery remain deferred, but that gate is enforced here, in agent-turn
> space, because no runtime seam exists that could enforce it later. Keep one
> data product in flight at a time while iterating.

## Route the request before doing work

Classify the request before provisioning, generation, or querying. Prefer the
smallest path that can give an honest answer:

| Situation | Route |
|---|---|
| **Explicit deployed/platform product** — the user names a remote DP, cluster, or platform endpoint | Hand off to `nxd-data-product-query`. Do not create a local replacement. |
| **Existing local product** — the task supplies its `semantic_endpoint` and bearer token | Call `mcp__nxd-desktop__describe_models`, then answer through `mcp__nxd-desktop__run_semantic_query`. |
| **Existing local product, but no endpoint/token** — the typical new session, since the bearer is per-session and never persisted | There is no list, status, or rediscovery MCP tool, so the running instance cannot be found. Locate the durable closure path (ask if unknown) and **reopen by rebuilding**: `build_data_product` with the same definition path and the same workflow id. This is a **mitigation that costs a full rebuild**, not a reattach — narrate it as such. See `reference/reopen.md`. |
| **In-scope source data** — attached/exported CSVs, another local file (JSON/JSONL/Parquet), a connected workspace folder, pasted tabular data, a spreadsheet, an accessible live database connection, or an off-mesh REST API the user describes | Preserve the source, infer a model, generate a local closure when no suitable local product exists, then answer through the supervisor. An ordinary single file source may be copied unchanged into the generated closure's required export layout; a database or API source is described (host/URL, credentials-availability, table/endpoint list), never fabricated, and its connection details pass through to generation exactly as the user gave them. Never modify a supplied original. |
| **No product and no source** | Ask one concise question naming the missing thing: the local data file/folder or an existing product to query. Do not manufacture a dataset, create a throwaway database, or probe Cowork uploads/workspaces with Bash in hope of finding one. |
| **Trivial, non-durable calculation** — for example, arithmetic over values pasted in the request, with no request to analyze or reuse data | Answer directly. Do not start a supervisor or build a product. |
| **Local analysis requested but runtime unavailable** | Stop before fallback work. State that the local analysis runtime is unavailable, identify the missing MCP connection or host-local runtime prerequisite, and point to `nxd-desktop-setup.sh` / the Desktop connection repair. Do not substitute SQLite, raw SQL, pandas, or shell aggregation. |

Treat ambiguous requests conservatively. If a question could mean either a
one-off calculation or analysis of an unseen source, ask which data or product
should answer it. If data is in scope and the user asks for a recurring,
shareable, or multi-question analysis, prefer the reusable local-product path.

## Choose the execution surface

Choose this order before invoking any runtime command:

1. **MCP first.** If all three tools are available —
   `mcp__nxd-desktop__build_data_product`,
   `mcp__nxd-desktop__describe_models`, and
   `mcp__nxd-desktop__run_semantic_query` — use them for the entire build,
   describe, and query sequence. This is the supported route for Claude
   Desktop and Claude Cowork.
2. **Direct CLI only on a confirmed host-local Darwin shell.** Use
   `nxd-desktop-supervisor` only when the session context has positively
   established that the shell is the user's macOS host **and** both
   `nxd-desktop-supervisor` and its sibling `nxd-desktop-kernel-host` are
   present together. If either fact is not already established, do not assume
   it from a path, home directory, or prior task.
3. **Otherwise stop.** Report that no usable local desktop runtime is connected
   and give the provisioning/connection recovery action.

In Claude Cowork, its workspace `Bash` is an isolated Linux environment. Use it
only to read, stage, or materialize task files. **Never run `uname`, binary
probes, or supervisor commands there**, and never use its Linux paths as MCP
definition paths. The connected `nxd-desktop` MCP server runs on the host and
is the runtime authority.

The `allowed-tools` frontmatter is restricted by this plugin's validator to
built-in tool names; it cannot enumerate fully qualified MCP tools. The three
`mcp__nxd-desktop__…` calls above are nevertheless mandatory whenever exposed
by the session tool registry.

## The loop — step by step

### Step 1 — Gather intent, source, and questions

Establish three things (ask the user for whatever is missing):

- **Intent** — what the data product is about, in the user's words.
- **Source** — where the in-scope local data lives. Preserve it exactly; if it
  is not already a connector export, keep any generated export copy separate
  from the supplied source.
- **Questions** — the natural-language questions the DP must answer. These drive
  the whole inference (right-to-left): the model is judged by whether it answers
  them.
- **Any procedure the user already has** — a rubric, gates, weights, thresholds,
  a verdict vocabulary, a selection rule. Ask for it here rather than inferring
  one later: a supplied procedure is the spec, encoded verbatim and landed as
  data, and a gap in it is a question back to the user. nxd-generate-dp's
  `reference/derivation-plan.md` owns how it lands.

Warm the user up before long work: state that you'll infer a model, generate the
DP, run it locally, and then answer their questions — so a multi-minute build is
expected, not a stall.

**Determine every source the data product needs before materializing.** A
data product may need exactly one source, or several — the same connector
type twice (two databases), or a mix (a database plus a REST API). For each
source, determine its connector type: local file(s) (CSV/JSON/JSONL/Parquet),
a live database connection, or an off-mesh REST API. Ask if it isn't already
stated; never assume database or API access exists just because a question
sounds analytical. If the user's request already states a source's connector
type and its details (a host, table names, a base URL), gather everything in
one turn instead of confirming the type first and then asking a second round
for its details — the "ask only for what's missing" discipline in the
bullets below applies to this gate too, not only to the Pasted-table case.

**The moment there is more than one source, give each a short, distinct
label** (lowercase, hyphenated, e.g. `orders`, `users`) and use it
consistently for the rest of the loop — nxd-generate-dp only *requires* a
label to avoid two same-type sources colliding on one fixed name, but
labeling every source once there are 2+ keeps the whole build unambiguous.
A single-source data product needs no label; do not invent one. This does
not conflict with "keep one data product in flight" above — that limits how
many data products you build at once, not how many sources one data product
may have.

Materialize each source faithfully before inference — repeat the matching
bullet once per source when there is more than one, tagging every artifact
you produce with that source's label. **If the request supplied a procedure
(rubric, gates, thresholds, verdicts) with a gap that changes a result, the
policy read-back in Step 3's skill comes FIRST** — reading a source is always
allowed, but copying it into a closure is a materialization and waits for the
user's reply:

- **Attached or workspace source:** make an exact byte-for-byte copy into the
  generated connector export. Do not rewrite delimiter, encoding, headers, or
  rows.
- **Pasted table:** materialize every supplied header and value faithfully in a
  separate CSV export. Do not add columns, coerce values, deduplicate rows, or
  invent an identifier. Treat introductory prose before or after a table as
  narrative, not a data row. A header followed by consistently shaped rows is
  sufficient evidence to proceed: do not claim a valid value was spliced,
  truncated, or missing merely because the chat renderer visually wraps the
  prompt. Ask only when the supplied table itself has a real structural
  ambiguity, such as a row with a different field count or an unparseable value.
- **Database connection:** record the host/port/database/schema, the
  table(s)/view(s) explicitly named by the user, and the live credentials
  (user/password) the user supplies now — nxd-generate-dp writes them into
  the generated `infra-profile.yaml`'s `db-source` service `attributes` (see
  `nxd-generate-dp's reference/database-source.md`, and `nxd-generate-dp's
  reference/multi-source.md` for the labeled-instance shape). Never invent a
  table name or fabricate a credential, and never narrate a live credential in
  chat — it goes into `infra-profile.yaml` and nowhere else.
- **REST API:** record the base URL, auth scheme, the endpoint(s)/resource(s)
  in scope, a sample response shape if available, any known pagination, and
  the live token/key/credentials if the API requires auth — nxd-generate-dp
  writes them into the generated `infra-profile.yaml`'s `api-source` service
  `attributes` (see `nxd-generate-dp's reference/api-source.md`, and
  `nxd-generate-dp's reference/multi-source.md` for the labeled-instance
  shape). Same rule as the database case: never fabricate a credential, never
  narrate a live one in chat.
- **Host path handoff:** pass `build_data_product` only the host-visible,
  absolute output path explicitly returned or exposed by the file-writing tool.
  Never derive a definition path from an opaque attachment ID, a tool-internal
  ID, or a Linux workspace path. If no host-visible absolute output path is
  available, stop and explain that the local build cannot access the materialized
  definition yet.

> **Fidelity here; derivation downstream.** The rules above govern **source
> materialization only**, and they are absolute: the CSVs you land are a
> byte-exact record of what the user supplied, so any later number can be
> traced back to it. Cleaning, deduplication, amortization, currency
> normalization, reclassification and regrain are all legitimate — and often
> necessary — but they exist **only as derived models computed downstream of
> the pristine source**, never as an edit to the source export. Never delete a
> duplicate, fix a value, add a column, or invent an identifier on the way in.
> Preserve the row, then derive the corrected model beside it. nxd-generate-dp
> owns how derived models are authored.

### Step 2 — Infer the semantic model

Invoke the **nxd-semantic-data-product** skill in its inference mode: profile
each source into `schema.json`, then derive the semantic model (grains,
dimensions, metrics, joins, PII) from the profile(s) **and** the user's
questions. With more than one source, profile each separately and carry its
label forward on every model it produces — Step 3 needs that mapping to know
which labeled source each physical model belongs to. That skill owns the
public semantic role grammar — follow it; do not duplicate its guidance here.

### Step 3 — Generate the runnable closure

Invoke the **nxd-generate-dp** skill: assemble the complete Python-authored
closure — `spec.py`, `models.py`, `infra-profile.yaml`, `transform/main.py`,
`requirements.txt`, `CONTEXT.md`, and the connector-type-specific artifact(s) — from the
intent, inferred model(s), and connector config. **That skill opens with a
policy read-back gate**: when the request carried a procedure with a gap that
changes a score, verdict, gate outcome, or which rows land, it writes nothing
until the user has seen the enumerated proposal and replied. Do not route around
it, and do not treat your own earlier technical questions as that approval. Pass through **every**
gathered source with its label (or the single unlabeled source, if there's
only one) and its per-model provenance from Step 2, untouched: the file
export plus `csv-source-path`/`file-source-path`, or the `db-source-tables`
mapping, or the `api-source-endpoints` mapping — one such artifact per
source, labeled per `nxd-generate-dp's reference/multi-source.md` when there's
more than one. **nxd-generate-dp owns the exact per-type (and per-instance)
shape — do not re-derive it here.** That skill owns the local DP shape (DuckDB
output port, dlt-in-transform, local executor), the naming invariant, and the
derived models that carry any business ruling the semantic layer cannot
express. **Never author `deployment-spec.yaml`, `manifest.yaml`, or
`models.yaml`: the supervisor compiles those build products from the Python
sources when it pins the definition.** Include instructions from the file
`reference/dlt.md`. The output is a **closure directory** — the `--definition`
argument for Step 4.

**Land the closure at a durable, user-visible path — never a temp or scratch
directory.** Put it in a directory named by the workflow id
(`…/nxd-pocket/<workflow>/`) on the file-writing surface, under whichever base
the host-visible-absolute-path rules in Step 1 make legal, and **state that
path to the user in the handoff**. There is no list, status, or rediscovery
MCP tool, and the bearer is minted per session and never persisted — so this
path is the only key a later session has to the product. A closure written to
a scratch dir is effectively lost when the session ends. See
`reference/reopen.md`. The closure's `CONTEXT.md` (emitted by nxd-generate-dp)
is the durable record a *later* session reads to continue the work — the reopen
recipe, the sample-selection rule, per-field inference caveats, and the full
contract of any promised-but-unbuilt derived model. It must be self-contained:
a derived model's contract lives inside the closure, never behind a `../` pointer
to an external doc that the handoff would strand.

**Relay the self-check's distribution read-back before building**, in one or two
lines: the value counts it printed for each classification column (a column that
came out uniform is the one to say out loud), and which of the closure's
assertions are internal-consistency only rather than checks against the source.
A green self-check means the closure is structurally sound and the transform
ran — never report it as evidence that the numbers are right.

### Step 4 — Build and serve through MCP

When the three desktop MCP tools are available, call
`mcp__nxd-desktop__build_data_product` with the host-visible absolute closure
path as `definition` and a stable `workflow`. It creates, publishes, and serves
the product for this MCP session. Treat the returned `semantic_endpoint` and
`bearer_token` as the only connection for later calls; keep the token out of
narration.

Fail closed on any build error or missing returned endpoint/token. Report the
MCP build failure and its actionable message; **do not retry through workspace
Bash, SQLite, raw SQL, pandas, or another local database.** A successful build
is the only proof that the generated product is ready to query.

Use the direct CLI only under the confirmed host-local Darwin conditions in
"Choose the execution surface." Keep that path equivalent: serve the generated
closure, retain its endpoint/token, and stop on any failure rather than falling
back to a different analysis mechanism.

### Step 5 — Answer the questions (NL → governed query)

The query surface is **structured** (measure/dimension names); the
natural-language translation is yours to do. For each question:

1. **Discover the catalog first.** Call
   `mcp__nxd-desktop__describe_models` with the endpoint/token returned by the
   build (or supplied for an existing local product). The declared vocabulary is
   canonical — map against it, do not guess concept names from source columns.
2. **Map the NL question to a selection.** Pick the measure(s) and dimension(s)
   that answer it — reuse the question→concept mapping approach from
   **nxd-data-product-query**'s semantic-layer section. Before running, restate
   the selection you chose and, if the question is ambiguous against the declared
   concepts, ask rather than silently picking.
3. **Check the question fits the MCP grammar.**
   `mcp__nxd-desktop__run_semantic_query` accepts `measures[]`, `dimensions[]`,
   `filters[]` (`=`, `!=`, `<>`, `>`, `>=`, `<`, `<=`, `LIKE`, `ILIKE`; ANDed
   only; values are strings), `order_by[]` (names must be among the selected
   measures/dimensions) and `limit` (capped at 200 rows). It does **not** support
   `IN`/`BETWEEN`/`IS NULL`/`NOT LIKE`, `HAVING` or measure-level filtering, `OR`,
   raw-row retrieval, or raw SQL.
   Apply the **Omission Test** to every constraint before you place it — see
   [reference/query-grammar.md](reference/query-grammar.md). Would a consumer who
   never heard the constraint, querying with no filters, get a **wrong** number
   (a **standing ruling** → materialize it in a derived model, Step 6) or merely a
   **broader** one (a **per-question constraint** → express it with
   `filters[]`/`order_by[]`/`limit` here)? When ambiguous, ask; with no user
   available, materialize. If a genuine per-question constraint outruns the
   grammar, use the sanctioned patterns in that reference (group-and-read,
   two ANDed filters for a range, `order_by`+`limit` for a threshold) — never
   re-aggregate agent-side, and never silently drop the constraint.
4. **Run the governed query.** Call
   `mcp__nxd-desktop__run_semantic_query` with the endpoint/token plus the
   selected measures and dimensions. Do not bypass it with raw SQL or a local
   aggregation.
5. **Quantify the review bucket before presenting a classified total.** If the
   selection's model carries a classification dimension with a review bucket
   (`needs_review`, `unmapped`, `other`), a single headline number hides how
   much of it is unclassified. Run the same measure grouped by that dimension
   and report the bucket's share alongside the total whenever it is nonzero —
   "€480k total; €190k (40%) is `needs_review`". A classified total with an
   unquantified review bucket is a preview, not an answer.
6. **Parse + present.** Render the returned rows as a compact table and state
   the semantic selection that produced them. Surface any ruling behind the
   answer: if a dimension you grouped by or filtered on carries a
   `describe_models` description naming a ruling (a mapping, an exclusion, a
   reclassification), state that ruling in the answer — the consumer is
   trusting it whether or not they know it exists. Label any partial or
   unverified result as a preview rather than the complete answer.

### Step 6 — Refine wrong answers back into the loop

If an answer is wrong, missing, or unsatisfying, decide where the fix belongs and
keep BOTH levels bounded:

- **Query-level** (cheapest) — the model is right but the selection was wrong or a
  dimension was missing. Re-describe, re-map, then re-query through MCP. Cap at
  ~2 remaps per question.
- **Model / DP-level** — the inferred model is wrong (missing metric, wrong grain,
  missing join, wrong PII), or the question needs a column or grain that does
  not exist yet (a filtered figure, a ratio, a monthly rollup, a
  classification). The latter is a **derived model**, not a query tweak: go back
  to Step 2/3 and have nxd-generate-dp materialize the ruling, then rebuild
  through MCP with the **same** `workflow`. Cap at ~3 regenerate cycles total.

**After every rebuild, refresh:** use the endpoint/token returned by that build,
then describe the catalog before mapping again — the regenerated model is exactly
when the catalog can differ. Define success as a catalog-grounded answer the user
accepts. If the loop does not converge within the caps, report what you tried,
what the product currently declares, and where the gap is — do not loop
indefinitely or give up silently.

## Narration discipline (always)

- **Warm up** before any multi-minute step (inference, generation, serve).
- **Per-step progress** — report entering each phase; never a silent stall.
- **Label previews as previews.** A sampled, partial, or `truncated` result is a
  preview, not a verified answer — say so. Never present an unvalidated
  intermediate as the final answer.
- **Show the query behind the answer** — every answer states the
  measure/dimension selection that produced it, and the ruling behind any
  dimension whose catalog description names one.

## Invariants — never violate these

- **Do not re-teach inference or code generation.** Invoke
  nxd-semantic-data-product and nxd-generate-dp.
- **Preserve supplied data.** Never modify an input file, its headers, or its
  rows; never add an identifier or fabricate a key. A generated file-connector
  export may contain only an exact copy kept separate from the supplied
  source. This governs **source materialization** and admits no exception.
  For a live database or REST API source, treat access as
  **read-only**: never write to the source, never fabricate a table/endpoint
  the user didn't name, and never invent or narrate a raw credential. A real
  credential is written exactly once — into the generated `infra-profile.yaml`
  connector service's `attributes` (nxd-generate-dp's job) — never anywhere
  else, and never into chat narration. This differs from the bearer-token
  invariant below, which is never written to any file at all. Once a
  credential is written there, **the closure directory itself is sensitive**
  — don't commit it, zip it, attach it to a ticket/chat, or reuse it as a
  template for a different source without clearing the old credential first.
- **Label every source once there are 2+.** A single-source data product
  needs no label. With multiple sources, each gets a short, distinct label
  used consistently across materialization, inference, and generation; never
  let two sources of the same connector type share an unlabeled or duplicate
  name — that's a collision nxd-generate-dp cannot resolve for you.
- **Correct data downstream, never upstream.** Cleaning, deduplication,
  amortization, currency normalization, reclassification and regrain belong in
  **derived models computed from the pristine source** — authored by
  nxd-generate-dp, landed through the DuckDB output port, and asserted in the
  transform. Never reach that outcome by editing the source export, and never
  emulate it agent-side over query results.
- **A judgement not in the data is confirmed and landed, not hardcoded.** FX
  rates, merchant→category rulings and similar mappings are surfaced to the
  user, confirmed, and landed as their own model so they are queryable — never
  embedded as constants in generated transform code.
- **A supplied procedure with a result-changing gap is read back BEFORE any
  materialization.** No closure directory, source copy, generated code, table,
  scoring, or build until the user has seen every proposed anchor, band and
  precedence rule and replied. A technical delivery question is not that
  approval; "use your judgement" licenses authoring the proposal, not skipping
  the turn.
- **A ruling behind a number is stated with the number.** When a dimension's
  catalog description names the ruling that created it, the answer says so, and
  a classified total reports its review-bucket share whenever nonzero. A
  governed answer that silently rests on an unstated ruling is the failure this
  loop exists to prevent.
- **Keep governed analysis on the supervisor path.** Never answer a governed
  local-data question with SQLite, `sqlite3`, raw SQL, pandas aggregation, or a
  shell pipeline as a fallback. The supervisor may compile semantic selections
  internally, but do not author or execute raw SQL to bypass its query contract.
- **MCP is authoritative when connected.** If the three `nxd-desktop` MCP tools
  are present, build, describe, and query through them. A failed MCP build is a
  reported failure, not permission to use a workspace-shell or database fallback.
- **Hand off only host-visible paths.** Pass `build_data_product` an absolute
  generated-definition path explicitly exposed by the file-writing surface;
  never infer one from an attachment ID or isolated Linux path.
- **Query is by measure/dimension name, not raw SQL or NL.** The NL→selection
  translation is agent-side; ground it in `describe_models`. The desktop MCP
  query contract accepts measures, dimensions, ANDed `filters[]`, `order_by[]`
  and `limit` — use them for **per-question scoping only**, and never emulate
  the grammar's gaps by re-aggregating agent-side.
- **A standing ruling materializes; a filter never enforces one.** Apply the
  **Omission Test** ([reference/query-grammar.md](reference/query-grammar.md)):
  if a consumer querying with no filters would get a *wrong* number, the ruling
  belongs in the transform, and the ruling-bearing measure must be correct with
  no filter applied. Landing an `is_transfer` dimension and expecting callers to
  filter on it is the same silent failure wearing a column. Only a constraint
  that would merely make the answer *broader* is a query-time filter.
- **One workflow id per data product.** Rebuild the same id to regenerate.
- **The supervisor data dir is off-limits.** Everything under `.pocket/state/`
  — pinned snapshots in `definitions/<id>/`, `state.sqlite*`, `staging/` — is
  immutable supervisor-owned state. Never `chmod`, edit, or hand-write those
  files to fix a closure. A concrete `.../staging/run-<id>/data.duckdb` path
  inside a pinned `manifest.yaml` is the supervisor's own resolved runtime path,
  not a defect. If a served closure is wrong, fix it in **your** source dir and
  re-`serve` — the supervisor re-pins a fresh snapshot.
- **Bearer only as a tool parameter.** Keep it out of narration and never persist
  or print it.
- **Never present a preview or truncated result as verified data**, and never
  stall silently.
- **The loop is bounded** — cap query remaps and regenerate cycles; report
  non-convergence.

## Reference skills

| Skill | Role in the loop |
|-------|------------------|
| `nxd-semantic-data-product` | Infers the semantic model from the source + questions (Step 2) |
| `nxd-generate-dp` | Generates the runnable local closure the supervisor serves (Step 3), including local-file, database, and REST API connector config — see its own `reference/` for the connector-type-specific shape. |
| `nxd-data-product-query` | Source of the question→concept mapping approach (Step 5) |
