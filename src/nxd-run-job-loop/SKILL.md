---
name: nxd-run-job-loop
description: THE ENTRY POINT for local business-data work — whether the user asks a question or asks to BUILD. Use when a task references tabular business data (CSVs, spreadsheets, exports, a live database, a REST API) and the user wants an analytical answer they may revisit (breakdown, ranking, comparison, trend, anomaly, driver) OR asks to build or generate a data product over it. A direct build request starts HERE, not in nxd-generate-data-product: this skill gathers intent, sources, questions, models, transform logic, explicit inputs and outputs, inline terms, decisions, and open questions into the prose-first editable dp-blueprint.md, then invokes the generator. Going straight to the generator skips the co-authoring checkpoint. Answer only from the product's semantic query result; never substitute raw SQL, pandas, or shell aggregation. Not for one-off arithmetic. For a deployed platform product, use nxd-query-data-product.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
metadata:
  author: nextdata
  version: 0.38.6
---

# nxd-run-job-loop skill

## Overview

This skill is the analyst-facing entry point for local business-data questions;
start from the user's outcome and available data, not internal product language.
When a durable local product is useful, drive the **local job loop**: a natural
language intent plus a local source become a running, queryable desktop product.

```
intent + sources + questions
   → author dp-blueprint.md, the IR    (user-editable; the policy read-back)
   → infer the semantic model          (nxd-build-semantic-data-product)
   → generate the runnable closure     (nxd-generate-data-product)
   → build + serve on the supervisor   (nxd-desktop MCP)
   → render the pinned static release  (nxd-render-static-artifact)
   → describe → translate NL → query → present → refine
```

This skill is the **orchestrator** and entry point for end-to-end builds.
`nxd-generate-data-product` constructs the closure after the plan is settled; if
you arrive there without Steps 1–1b, come back here first. It invokes the owning
skills, then drives the supervisor MCP path — routing the user never sees.

> **You own the conversation and sequencing**, except for the policy read-back
> discharged by the approved `dp-blueprint.md` in Step 1b. Keep one data product in
> flight at a time while iterating.

## Route the request before doing work

Classify the request before provisioning, generation, or querying, and prefer the
smallest path that gives an honest answer — the routing table, step order, caps,
the one-DP-in-flight rule and the subagent fan-out are in
[reference/scheduling.md](reference/scheduling.md). The two routes that decide
the whole loop: **a source is in scope with no suitable local product** → run the
loop end to end; **an existing local product but no live endpoint/token** (the
typical new session, since the bearer never persists) → **reattach, don't
rebuild**: `list_data_products` → `resume_data_product` → artifact.
`list_data_products` is discovery only and must never supply a static-artifact
fallback ([reference/context-and-resume.md](reference/context-and-resume.md)).
Treat ambiguity conservatively: when a request could mean either a one-off
calculation or analysis of an unseen source, ask which should answer it, and
prefer the reusable local-product path for recurring or multi-question work.

## Choose the execution surface

Choose this order before invoking any runtime command:

1. **MCP first.** Read the server's `tools/list` catalog when the client exposes it; this hand-maintained workflow list is not exhaustive. The current seven loop tools are `mcp__nxd-desktop__check_data_product`,
   `mcp__nxd-desktop__build_data_product`, `mcp__nxd-desktop__resume_data_product`,
   `mcp__nxd-desktop__list_data_products`, `mcp__nxd-desktop__describe_models`,
   `mcp__nxd-desktop__run_semantic_query`, and `mcp__nxd-desktop__inspect_run`
   — use them for the entire discover, build, resume, describe, and query
   sequence, plus a read-only `mcp__nxd-desktop__export_data_product` for
   on-demand handoffs. **`inspect_run` is the failed-build diagnostic**: call it
   **once** with the failed `run_id` rather than classifying from the build error
   text — [reference/failure-handling.md](reference/failure-handling.md) § After a
   failed build has the contract and the rules.
   This is the supported route for Claude Desktop and Claude Cowork. Read-only `nxd://`
   **resources** — with tool bridges where a client exposes none — expose what a
   release *declares*: [reference/catalog-resources.md](reference/catalog-resources.md).
2. **Direct CLI only on a confirmed host-local Darwin shell.** Use
   `nxd-desktop-supervisor` only when the session context has positively
   established that the shell is the user's macOS host **and** both
   `nxd-desktop-supervisor` and its sibling `nxd-desktop-kernel-host` are
   present together. If either fact isn't already established, don't assume it
   from a path, home directory, or prior task.
3. **Otherwise stop.** Report that no usable local desktop runtime is connected
   and give the provisioning/connection recovery action.

In Claude Cowork, its workspace `Bash` is an isolated Linux environment — use it
only to read, stage, or materialize task files. **Never run `uname`, binary
probes, or supervisor commands there**, and never use its Linux paths as MCP
definition paths: the connected `nxd-desktop` MCP server runs on the host and is
the runtime authority. This plugin's validator restricts `allowed-tools` to
built-in names and cannot list MCP tools; the `mcp__nxd-desktop__…` calls above
are mandatory anyway whenever the session registry exposes them.

## The loop — step by step

### Step 1 — Gather intent, sources, questions, and output needs

Establish the following (ask the user for whatever is missing):

- **Intent** — what the data product is about, in the user's words.
- **Sources** — where the in-scope local data lives. Preserve each source exactly; if it
  is not already a connector export, keep any generated export copy separate
  from the supplied source.
- **Questions** — the natural-language questions the DP must answer. These
  drive the whole inference (right-to-left): the model is judged by whether it
  answers them.
- **Models, transform logic, and outputs** — what named relations should exist,
  which typed operations produce them, which questions each Output answers, and
  where each Output is delivered.
- **Any procedure the user already has** — capture it as a versioned procedure
  on a Transform step or reference Model. Decisions record provenance and
  rationale; they are never executable policy. If it is already written down,
  translate the document rather than asking the user to re-state it.

Warm the user up before long work: state you'll write the spec, generate the DP,
run it locally, then answer their questions — a multi-minute build is expected,
not a stall. **Determine every source the data product needs before
materializing.** A product may need one source or several — the same connector
type twice, or a mix (a database plus a REST API). For each, determine its
connector type: local file(s) (CSV/JSON/JSONL/Parquet), a live database
connection, or an off-mesh REST API. Ask if not already stated; never assume
database or API access exists because a question sounds analytical. If the
request already states a source's type and details, gather it all in one turn.

**The moment there is more than one source, give each a short, distinct label**
(lowercase, hyphenated, e.g. `orders`, `users`) and use it consistently for the
rest of the loop; a single-source data product needs none, so don't invent one.
The one-product-in-flight rule above limits how many products you build at once,
never how many sources one may have. Materialize each source faithfully before
inference — repeat the matching bullet once per source, tagging every artifact
with that source's label. **If the request supplied a procedure (rubric, gates,
thresholds, verdicts) with a gap that changes a result, the policy read-back in
Step 3's skill comes FIRST** — reading a source is always allowed, but copying it
into a closure is a materialization and waits for the user's reply. Per-kind
rules — attached file, pasted table, database, REST API, and the host-path
handoff — plus where credentials land are in
[reference/source-materialization.md](reference/source-materialization.md),
which also carries the absolute **fidelity here; derivation downstream** rule —
landed rows are byte-exact, and every correction is a derived model beside the
pristine source, never an edit to it.

### Step 1b — Author `dp-blueprint.md`, the prose-first user plan

Write what Step 1 gathered into **`dp-blueprint.md`** at
`…/nxd-jobs/<workflow>/dp-blueprint.md`, beside the closure (which lands at
`closure/`). The user-facing document uses the fixed, ordered sections Intent,
Questions, Scope, Terms, Inputs, Models, Transform, Outputs, Decisions, and
Open Questions. Keep the headings strict but allow ordinary prose, lists,
tables, examples, and code blocks within them. The user must never be asked to
write or inspect the terse typed proposal. Schema, Terms behavior, editing
rules, and the Claude Desktop form contract are in
[reference/dp-blueprint.md](reference/dp-blueprint.md).

**If the user supplied a doc** — a build spec, a rubric page, or a prose
description — preserve its meaning in the Markdown and show what you filled in.
Do not force the user to translate it into labelled fields. Put expectations
under Inputs, promises under Outputs, and behavior-affecting decisions in
Transform. Terms are inline in this document; do not create or depend on an
external Glossary DP. Delivery is the platform-fixed local DuckDB semantic
query path, not a user-authored section. Executable contracts are compiled
internally from the Input expectations and Output promises.

After writing or editing the document, run the structural validator:

```bash
python3 "$JOB_HELPER_DIR/scripts/validate_dp_spec.py" <path>/dp-blueprint.md --json
python3 "$JOB_HELPER_DIR/scripts/dp_spec_authoring.py" validate <path>/dp-blueprint.md --json
```

The deterministic parser only checks headings, free prose, source spans, and
lifecycle metadata. Then have the AI produce a typed proposal with
`explicit`, `inferred`, or `platform_fixed` provenance, source spans, compiled
contracts, the fixed delivery profile, and a complete natural-language
echo-back. Deterministic proposal validation must turn underspecification into
an Open Question; it must never accept confidence as correctness.

**Approval is approval of the echo-back.** A validator pass is not approval,
and `status: approved` is the user's decision. Approval binds the Markdown and
typed proposal hashes plus Terms, contract-inventory, compiler, and delivery
metadata. Lock each approved Decision by id and hash; extraction may not
overwrite it. A conflicting edit becomes an explicit change proposal and
revokes approval. The approved Markdown and typed proposal are byte-snapshotted
into the closure, never referenced through `../dp-blueprint.md`.

When a question needs a judgement read from each entity's evidence, model that
decision as a versioned `apply_procedure` Transform step or reference Model.
The result is a named Model exposed through an Output; the Decisions ledger
remains provenance only.

### Step 2 — Infer the semantic model

Invoke the **nxd-build-semantic-data-product** skill in its inference mode: profile
each source into `schema.json`, then derive the semantic model — grains,
dimensions, metrics, joins, PII, **and a description on every model, dimension
and metric** (Step 5 reads them to map questions) — from the profile(s), the
user's questions, and the spec's `models:` plan. With 2+ sources profile each
separately, carrying labels forward. That skill owns the role grammar.

### Step 3 — Generate the runnable closure

Invoke the **nxd-generate-data-product** skill: assemble the complete Python-authored
closure — `spec.py`, `models.py`, `infra-profile.yaml`, `transform/main.py`,
`requirements.txt`, `dp-blueprint.approved.md`, `dp-blueprint.lock.json`,
`build-record.json`, `README.md`, and the connector-type-specific artifact(s) —
from the **approved `dp-blueprint.md`** (Step 1b), the inferred model(s), and the
connector config. Pass the spec's path: it carries the intent, questions, model
plan and every ruling, so the generator compiles rather than re-derives, and the
`decisions:` block becomes `nxd_decisions` row for row. **That skill opens with a
policy read-back gate**: when the request carried a procedure with a gap that changes a score, verdict, gate outcome, or which rows land, it writes nothing
until the user has replied — the approved spec discharges it, so don't route
around it. Pass through **every** gathered source with its label
(or the single unlabeled source) and its per-model provenance from Step 2,
untouched — one artifact per source, labeled per `nxd-generate-data-product`'s
`reference/multi-source.md` when there's more than one. **That skill owns the
exact per-type shape — don't re-derive it here**, along with the local DP shape
(DuckDB output port, dlt-in-transform, local executor), the naming invariant, and
the derived models carrying any business ruling the semantic layer can't express
— its own `reference/` holds the connector-type-specific shape, and that skill's
`reference/llm-judgments.md` holds how an agent judgement lands as data.
Pass the bootstrap-resolved absolute `job_helper_dir` too; this is a required
generator handoff field, not a path it may reconstruct from its own cwd.
**Never author `deployment-spec.yaml`, `manifest.yaml`, or `models.yaml`: the
supervisor compiles those from the Python sources when it pins the definition.**
Include `reference/dlt.md`'s instructions. The output is a **closure directory** —
the `--definition` argument for Step 4.

**Steps 2–3 MAY be offloaded to isolated subagents** — a profile subagent and a
separate generate subagent, split at the inference/authoring seam, never one
combined unit — but only when generation would otherwise dominate the main
context. Policy read-back and review relay stay main-thread: show every claim/effect and wait before behavior-affecting change.
Auto-fix only an evidenced syntax/mechanical/procedural structural correction with approved spec, models, grain, rows, values, aggregation, thresholds, verdicts and asserts unchanged.
A timeout needs explicit user consent. No live credential enters either subagent. Seam and boundary:
[reference/scheduling.md](reference/scheduling.md).

**Land the closure at a durable, user-visible path — never a temp or scratch
directory.** Put it under a directory named by the workflow id, with the IR
beside it: `…/nxd-jobs/<workflow>/dp-blueprint.md` and
`…/nxd-jobs/<workflow>/closure/` — the latter is what `build_data_product`
receives. Use whichever base the host-visible-path rules in Step 1 make legal,
and **state both paths to the user in the handoff**. The bearer never persists,
so a later session reattaches by **workflow id** (`list_data_products` →
`resume_data_product`) while the **closure path** keys the rebuild fallback when
the published artifact is gone
([reference/context-and-resume.md](reference/context-and-resume.md)) — naming the
dir by the workflow id keeps the two recoverable from each other. The durable
record a later session reads is **generated, never hand-written**: the approved
spec byte-copied in as `dp-blueprint.approved.md`, `dp-blueprint.lock.json` carrying its
hash and the compiler version, and `build-record.json` carrying what happened —
stages, attempts, concessions, blockers, the read-back. Self-containment is
checked against the lock rather than trusted: a derived model's contract lives
inside the closure, never behind a `../` pointer the handoff would strand —
`../dp-blueprint.md` included, since the IR is upstream of the closure, not a
dependency of it. **Relay the distribution read-back before building** in one or
two lines — the per-classification-column value counts (call out a uniform one),
and which assertions are internal-consistency only rather than checks against the
source; it is recorded in `build-record.readback`, relayed verbatim, non-gating.
A green self-check means the closure is structurally sound and the transform ran
— never evidence the numbers are right.

### Step 4 — Build and serve through MCP

Before build, call `mcp__nxd-desktop__check_data_product` with the same definition and workflow; it is read-only, reports provenance plus structure/runtime/contract/semantic findings, and uses stable finding codes. Treat `skip` as non-pass, stop on `fail`/`skip`, handle warnings, and allow ~330s; on confirmed host-local Darwin use `nxd-desktop-supervisor check --definition <dir> --workflow <workflow> --json` with identical inputs. See [reference/catalog-resources.md](reference/catalog-resources.md).
Then call `mcp__nxd-desktop__build_data_product` with the host-visible absolute path of the
`closure/` directory as `definition` and a stable `workflow`; it creates,
publishes, and serves the product for this MCP session. **If a subagent authored
the closure (Step 3), verify its returned path resolves on the supervisor's host
surface and the required closure files exist under it before building** — a
subagent writes to its own session surface and cannot guarantee the host sees
that path ([reference/scheduling.md](reference/scheduling.md)). Treat the
returned `semantic_endpoint` and `bearer_token` as the only connection for later
calls; keep the token out of narration. Building the same workflow again
regenerates it, while **resuming** an already-published one is the fast reattach
([reference/context-and-resume.md](reference/context-and-resume.md)), not a
rebuild. Fail closed on any build error or missing endpoint/token: report the
failure and its actionable message, and **do not retry through workspace Bash,
SQLite, raw SQL, pandas, or another local database** — a successful build is the
only proof the product is ready to query. The direct CLI is used only under the
confirmed host-local Darwin conditions above, kept equivalent: same closure
served, same stop-on-failure. **A build failure is not
evidence of a bad machine**: the supervisor compiles code the offline self-check
never executes, so a real code fault arrives wearing an environment's clothes.
Absent a supervisor-reported error body it is yours — heal, record the attempt,
and never claim an "environment issue" you cannot evidence
([reference/failure-handling.md](reference/failure-handling.md)).

#### Host-local direct CLI lifecycle

The confirmed host-local Darwin fallback is one foreground
`nxd-desktop-supervisor serve` process. Treat its `published=yes` metadata as
the only publication receipt, then run `status` and `describe` before querying;
keep the bearer out of narration. For bounded observation, failure handling,
and stop-on-failure rules, follow [reference/direct-cli-lifecycle.md](reference/direct-cli-lifecycle.md).

### Step 4a — Render the pinned static artifact

After every successful build or resume, invoke **nxd-render-static-artifact** for the
workflow before `describe_models` or any query. It reads only the current,
verified and outputs documents — over `nxd://` resources or the bridge tools —
and writes one self-contained release HTML file. Report artifact `status`, `path`
and `publish_seq` separately from the endpoint; on failure report it but keep a
healthy endpoint usable for describe/query. With an endpoint but **no workflow**,
say the artifact is unavailable and query on. A rebuild discards cached URIs and
renders its new sequence.

### Step 5 — Describe, query, and present

The query surface is **structured** (measure/dimension names); the
natural-language translation is yours to do. For each question:

1. **Describe the served catalog first.** Call `mcp__nxd-desktop__describe_models`
   with the endpoint/token returned by the build (or supplied for an existing
   local product) — the declared vocabulary is canonical, don't guess concept
   names from source columns.
2. **Map the NL question to a selection.** Pick the measure(s)/dimension(s) that
   answer it — reuse the question→concept mapping approach from
   **nxd-query-data-product**'s semantic-layer section. Restate the selection
   before running and, if it is ambiguous against the declared concepts, ask
   rather than silently picking.
3. **Check the question fits the MCP grammar.**
   `mcp__nxd-desktop__run_semantic_query` accepts `measures[]`, `dimensions[]`,
   ANDed `filters[]`, `order_by[]` and `limit` — no `OR`, no measure-level
   filtering, no raw rows, no SQL. The operator list, the sanctioned workarounds
   and the **Omission Test** are in
   [reference/query-grammar.md](reference/query-grammar.md). Apply that test to
   every constraint first: would a consumer querying with no filters get a
   **wrong** number (a **standing ruling** → materialize it, Step 6) or merely a
   **broader** one (a **per-question constraint** → express it here)? When
   ambiguous, ask; with no user, materialize. Never re-aggregate agent-side, and
   never silently drop the constraint.
4. **Run the governed query.** Call `mcp__nxd-desktop__run_semantic_query` with the endpoint/token plus the selected measures/dimensions — don't bypass it with raw SQL or a local aggregation. For ranked questions, pass endpoint-native `order_by: [{"name": "<selected measure or dimension>", "dir": "desc"}]` and integer `limit`; never sort or truncate rows agent-side.
5. **Quantify the review bucket before presenting a classified total.** If the
   selection's model carries a classification dimension with a review bucket
   (`needs_review`, `unmapped`, `other`), a single headline number hides how much
   is unclassified. Run the same measure grouped by that dimension and report the
   bucket's share alongside the total whenever nonzero — "€480k total; €190k
   (40%) is `needs_review`". An unquantified review bucket is a preview.
6. **Parse + present.** Render the returned rows as a compact table and state the
   semantic selection that produced them. Surface any ruling behind the answer:
   if a dimension grouped by or filtered on carries a `describe_models`
   description naming a ruling (a mapping, an exclusion, a reclassification),
   state it in the answer — the consumer trusts it whether or not they know it
   exists. Label any partial or unverified result as a preview.

### Step 6 — Refine wrong answers back into the loop

If an answer is wrong, missing, or unsatisfying, decide where the fix belongs.
Every level is **bounded**, and the bounds are **counted** from
`build-record.json` `attempts[]`, never estimated — remap ≤~2/question,
regenerate ≤~3 total, environmental retry ≤~3. Each attempt ends in one typed
exit: `healed`, `healed_with_concessions`, `caps_exhausted`, `blocked`,
`retry_environmental` ([reference/failure-handling.md](reference/failure-handling.md)):

- **Query-level** (cheapest) — the model is right but the selection was wrong or a
  dimension was missing. Re-describe, re-map, re-query through MCP.
- **Model / DP-level** — the inferred model is wrong (missing metric, wrong
  grain, missing join, wrong PII, an undistinguishing description), or the
  question needs a column or grain that doesn't exist (a filtered figure, a
  ratio, a monthly rollup, a classification) — a **derived model**, not a tweak.
  **Edit `dp-blueprint.md` first**, re-validate, and re-approve it when the change
  touches a ruling (a criteria change is a new `rubric_version`); then go back to
  Step 2/3 and rebuild through MCP with the **same** `workflow`. **After every
  rebuild, refresh:** discard cached artifact resources and current file, render
  the new release, then re-describe before mapping again. If the loop doesn't
  converge within the caps, report what you tried, what the product declares, and
  where the gap is ([reference/scheduling.md](reference/scheduling.md)) — never
  loop indefinitely or give up silently.
- **Blocked** — the fix is a ruling only the user can make (a missing rate, an
  ambiguous scope, a measurement no source carries). That is an open question
  found late, not a heal: write it back into `dp-blueprint.md`'s `## Open Questions`
  with what it blocks, which **un-approves** the spec; ask the one smallest
  question and re-enter Step 1b. Never reach green by changing the plan.

## Narration discipline (always)

You are the middleman. The user hears **exactly two classes** — **blockers** ("I
need something from you") and **concessions** ("I did something you should know
about"); everything else you absorb into one plain line of outcome. **Who owns a
problem decides whether it is spoken, not how severe it is**: an error you can
fix yourself is absorbed, a warning that is a concession is said out loud. Never
put a stage name, phase letter, diagnostic code or hash in front of the user.
Full rules: [reference/failure-handling.md](reference/failure-handling.md).

- **Warm up** before any multi-minute step (inference, generation, serve), and
  report entering each phase — never a silent stall.
- **Label previews as previews, and never present green as right.** A sampled,
  partial, or `truncated` result is a preview, not a verified answer; a build
  that passed is "built and checked", never "the numbers are correct".
- **Show the query behind the answer, and the ruling behind the query** — every
  answer states the measure/dimension selection that produced it, plus the ruling
  behind any dimension whose catalog description names one.
- **Disclose proposed judgement, and quantify the unscored bucket.** An answer
  resting on a model an agent judgement `applies_to` says so ("built on proposed
  agent judgements, rubric v1"), never as confirmed fact, and reports the unscored
  share like a `needs_review` share — a score over a silently-incomplete
  population is a preview.

## Invariants — never violate these

- **Preserve supplied data.** Never modify an input file, its headers, or its
  rows; never add an identifier or fabricate a key. A generated file-connector
  export may contain only an exact copy kept separate from the source — this
  governs **source materialization**, no exception. Treat a live database or REST
  API source as **read-only**: never write to it, never fabricate a
  table/endpoint the user didn't name, never invent or narrate a raw credential.
  A real credential lands in exactly one place — the generated
  `infra-profile.yaml` connector service's `attributes` — never elsewhere, never
  in chat, never in `dp-blueprint.md`, which names key names only. **"Never in chat"
  covers a value you invited there**: ask for *slot names*; the value reaches the
  profile off-transcript, via a placeholder the user fills in ([reference/source-materialization.md](reference/source-materialization.md)). Once landed, **the
  closure directory itself is sensitive**: don't commit, zip, attach, or reuse it
  as a template without first clearing the old credential, and *share* it only
  through `export_data_product` — never a hand-zip, because its fail-closed
  redaction is the credential boundary
  ([reference/handoff-export.md](reference/handoff-export.md)).
- **Label every source once there are 2+.** A single-source data product needs no
  label. With multiple sources each gets a short, distinct label used
  consistently across materialization, inference, and generation; two sources of
  the same connector type sharing an unlabeled or duplicate name is a collision
  nxd-generate-data-product can't resolve for you.
- **Correct data downstream, never upstream.** Cleaning, deduplication,
  amortization, currency normalization, reclassification and regrain belong in
  **derived models computed from the pristine source** — authored by
  nxd-generate-data-product, landed through the DuckDB output port, asserted in the
  transform. Never edit the source export to reach that outcome, never emulate it
  agent-side.
- **A judgement not in the data is confirmed and landed, not hardcoded.** FX
  rates, merchant→category and similar mappings are surfaced, confirmed, and
  landed as their own queryable model — never embedded as transform constants.
  **This covers agent-produced judgement too** — a per-entity
  score/verdict/classification read from evidence, landed agent-side as data
  (`status = proposed`, evidence-cited, rubric taught first); the build never
  invokes a model, and a baked-in judgement is hardcoded even when weighted.
- **A supplied procedure with a result-changing gap is read back BEFORE any
  materialization.** No closure directory, source copy, generated code, table,
  scoring, or build until the user has seen every proposed anchor, band and
  precedence rule and replied. A technical delivery question is not approval;
  "use your judgement" licenses authoring the proposal, not skipping the turn.
- **The plan is a file before it is code.** Every build is preceded by a
  `dp-blueprint.md` (Step 1b) written beside the closure, never inside it, and passed
  to the generator. A user-supplied value in it is encoded verbatim; a value you
  authored is marked `agent_authored` and named in the read-back; `status:
  approved` is the user's to set, never yours. Run
  `"$JOB_HELPER_DIR/scripts/validate_dp_spec.py"` after the scripts bootstrap
  before the read-back and again before generating — a validator pass only means
  compilable, never approved. What the user approves is what the generator
  byte-copies and hashes into the closure.
- **A heal changes generated code, never the plan.** The self-heal loop may
  rewrite `transform/main.py`, `models.py` or `spec.py`; it may never edit
  `dp-blueprint.md` to make a build pass. Narrowing the population to dodge a bad
  join, dropping a model whose grain won't resolve, relaxing a threshold — those
  are spec edits needing re-approval, and the build record catches one
  mechanically. Escalate instead of quietly re-planning.
- **Never claim green over an undisclosed concession, and say `materialized`,
  never `correct`.** A run that reached green by doing something the skills
  discourage is finished only once the user has heard what and why. Green means
  the approved plan compiled, ran and published — never that the numbers are
  right, and a ruling behind a number is always stated with the number.
- **Keep governed analysis on the supervisor path, and MCP is authoritative when
  connected.** Discover, check, build, resume, describe and query through the
  `nxd-desktop` tools whenever present. Never answer a governed local-data
  question with SQLite, raw SQL, pandas, or a shell pipeline as fallback, and
  never author raw SQL to bypass the semantic layer — a failed MCP build is a
  reported failure, not permission to route around it.
- **Reattach, don't rebuild, when the artifact is live, and keep one workflow id
  per data product.** In a fresh session with no endpoint, `list_data_products` →
  `resume_data_product` → static artifact recovers a published workflow in
  seconds with a fresh bearer; `list_data_products` remains discovery only;
  rebuild only when `collected` / `artifact_unavailable`. Rebuilding the same id
  regenerates one product; a different id is a different product and replaces the
  current endpoint ([reference/context-and-resume.md](reference/context-and-resume.md)).
- **Hand off only host-visible paths.** Pass `build_data_product` an absolute
  generated-definition path explicitly exposed by the file-writing surface; never
  infer one from an attachment ID or isolated Linux path, and verify a generation
  subagent's returned path host-side before build.
- **A subagent never owns the policy turn and never holds a credential.** When
  generation is offloaded (Step 3), the policy read-back stays a main-thread user
  turn — a subagent returns `gap_found` on a new gap instead of opening one; a
  live credential is placeholdered in the subagent and injected host-side before build, never in its prompt, return, or narration ([reference/scheduling.md](reference/scheduling.md)).
- **Query is by measure/dimension name, and a standing ruling materializes — a
  filter never enforces one.** Ground the NL→selection translation in
  `describe_models`; `filters[]`, `order_by[]` and `limit` are for **per-question
  scoping only**, never emulated by re-aggregating agent-side. Apply the
  **Omission Test** ([reference/query-grammar.md](reference/query-grammar.md)):
  if no-filter querying would get a *wrong* number the ruling belongs in the
  transform, and the ruling-bearing measure must be correct unfiltered. Landing an
  `is_transfer` dimension and expecting callers to filter on it is that same
  silent failure wearing a column.
- **The supervisor data dir is off-limits.** Everything under the supervisor's
  `--data-dir` (its `state/` tree) —
  pinned snapshots in `definitions/<id>/`, `state.sqlite*`, `staging/` — is immutable supervisor-owned state; never `chmod`, edit, or hand-write it, and a
  `.../staging/run-<id>/data.duckdb` path inside a pinned `manifest.yaml` is its
  own resolved runtime path, not a defect. If a served closure is wrong, fix
  **your** source dir and re-`serve` — the supervisor re-pins.
- **Bearer only as a tool parameter** — keep it out of narration, never persist or print it. **Never present a preview or truncated result as verified data**, and never stall silently.

## Reference docs (this skill)
Use [dp-blueprint](reference/dp-blueprint.md), [build record](reference/build-record.md), [failure handling](reference/failure-handling.md), [direct CLI lifecycle](reference/direct-cli-lifecycle.md), [source materialization](reference/source-materialization.md), [scripts bootstrap](reference/scripts-bootstrap.md), [scheduling](reference/scheduling.md), [context and resume](reference/context-and-resume.md), [inference](reference/inference.md), [handoff export](reference/handoff-export.md), [catalog resources](reference/catalog-resources.md), [query grammar](reference/query-grammar.md), and [dlt](reference/dlt.md) for named details.
