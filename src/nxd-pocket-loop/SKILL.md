---
name: nxd-pocket-loop
description: Use when a task includes or references tabular business data—rows, columns, CSVs, spreadsheets, or exports—and the user wants an analytical answer they may revisit: a breakdown, ranking, comparison, total by group, trend, anomaly, driver, or follow-up question. Treat recurring data, requests to keep asking questions, and repeated analysis as strong signals to create or reuse a governed local product, even when the first table is small enough to calculate directly. Answer only from the product's semantic query result. If the data or local desktop runtime is unavailable, state the missing prerequisite; never silently substitute raw SQL, pandas, shell aggregation, or mental arithmetic. Do not use for clearly one-off arithmetic with no tabular analysis or reusable intent. For an explicitly deployed platform product, use nxd-data-product-query.
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
  version: 0.11.0
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

This skill is the **orchestrator**. It does not re-teach inference or code
generation — it invokes the skills that own those, then drives the supervisor
MCP path to run and query the result. Do not expose this routing machinery as a
requirement for the user.

> **You own the loop, not the gates.** This skill sequences the work loosely and
> narrates progress. It does NOT enforce ordered approval gates or autonomy
> budgets — that hardening lives supervisor-side and is deferred. Keep one data
> product in flight at a time while iterating.

## Route the request before doing work

Classify the request before provisioning, generation, or querying. Prefer the
smallest path that can give an honest answer:

| Situation | Route |
|---|---|
| **Explicit deployed/platform product** — the user names a remote DP, cluster, or platform endpoint | Hand off to `nxd-data-product-query`. Do not create a local replacement. |
| **Existing local product** — the task supplies its `semantic_endpoint` and bearer token | Call `mcp__nxd-desktop__describe_models`, then answer through `mcp__nxd-desktop__run_semantic_query`. Without both endpoint and token, there is no list/status MCP tool: ask for the product connection or build from an in-scope source. |
| **In-scope source data** — attached/exported CSVs, a connected workspace folder, pasted tabular data, or a spreadsheet made available to the task | Preserve the source, infer a model, generate a local closure when no suitable local product exists, then answer through the supervisor. An ordinary single CSV may be copied unchanged into the generated closure's required export layout; never modify the supplied original. |
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

Warm the user up before long work: state that you'll infer a model, generate the
DP, run it locally, and then answer their questions — so a multi-minute build is
expected, not a stall.

Materialize the source faithfully before inference:

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
- **Host path handoff:** pass `build_data_product` only the host-visible,
  absolute output path explicitly returned or exposed by the file-writing tool.
  Never derive a definition path from an opaque attachment ID, a tool-internal
  ID, or a Linux workspace path. If no host-visible absolute output path is
  available, stop and explain that the local build cannot access the materialized
  definition yet.

### Step 2 — Infer the semantic model

Invoke the **nxd-semantic-data-product** skill in its inference mode: profile the
local source into `schema.json`, then derive the semantic model (grains,
dimensions, metrics, joins, PII) from the profile **and** the user's questions.
That skill owns the public semantic role grammar — follow it; do not duplicate
its guidance here.

### Step 3 — Generate the runnable closure

Invoke the **nxd-generate-dp** skill: assemble the complete Python-authored
closure — `spec.py`, `models.py`, `infra-profile.yaml`, `transform/main.py`,
`requirements.txt`, `csv-source-path`, and the unchanged CSV export copy — from
the intent, inferred model, and connector config. That skill owns the local DP
shape (DuckDB output port, dlt-in-transform, local executor) and the naming
invariant. **Never author `deployment-spec.yaml`, `manifest.yaml`, or
`models.yaml`: the supervisor compiles those build products from the Python
sources when it pins the definition.** The output is a **closure directory** —
the `--definition` argument for Step 4.

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
   `mcp__nxd-desktop__run_semantic_query` accepts only `measures[]` and
   `dimensions[]`. It does not support filters, ordering, raw-row retrieval, or
   raw SQL. If the request cannot be represented without dropping a constraint,
   explain the gap and clarify; do not broaden the answer silently.
4. **Run the governed query.** Call
   `mcp__nxd-desktop__run_semantic_query` with the endpoint/token plus the
   selected measures and dimensions. Do not bypass it with raw SQL or a local
   aggregation.
5. **Parse + present.** Render the returned rows as a compact table and state
   the semantic selection that produced them. Label any partial or unverified
   result as a preview rather than the complete answer.

### Step 6 — Refine wrong answers back into the loop

If an answer is wrong, missing, or unsatisfying, decide where the fix belongs and
keep BOTH levels bounded:

- **Query-level** (cheapest) — the model is right but the selection was wrong or a
  dimension was missing. Re-describe, re-map, then re-query through MCP. Cap at
  ~2 remaps per question.
- **Model / DP-level** — the inferred model is wrong (missing metric, wrong grain,
  missing join, wrong PII). Go back to Step 2/3, then rebuild through MCP with
  the **same** `workflow`. Cap at ~3 regenerate cycles total.

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
  measure/dimension selection that produced it.

## Invariants — never violate these

- **Do not re-teach inference or code generation.** Invoke
  nxd-semantic-data-product and nxd-generate-dp.
- **Preserve supplied data.** Never modify an input file, its headers, or its
  rows; never add an identifier or fabricate a key. A generated connector
  export may contain only an exact copy kept separate from the supplied source.
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
  query contract accepts only measures and dimensions — do not emulate filters
  or ordering outside it.
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
| `nxd-generate-dp` | Generates the runnable local closure the supervisor serves (Step 3) |
| `nxd-data-product-query` | Source of the question→concept mapping approach (Step 5) |
| `nxd-adding-inputs` / `nxd-adding-outputs` | Connector/port config guidance when assembling the closure |
