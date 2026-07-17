---
name: nxd-pocket-loop
description: Drives the end-to-end Nexty Pocket loop on a local desktop supervisor — turn a natural-language intent plus a local data source into a running, queryable data product, then answer the user's questions against it and refine when answers are wrong. Orchestrates the whole flow: infer the semantic model from the source and questions, generate the runnable data-product closure, boot and publish it on the local supervisor, translate NL questions into governed queries, and loop wrong answers back into a regenerate. Use when the user wants to "build a data product from a question", "spin up a local data product and ask it questions", "go from a CSV plus questions to answers", or iterate on a locally-generated DP. This is the orchestrator above nxd-semantic-data-product (inference) and nxd-generate-dp (code generation); it drives them plus the desktop supervisor CLI. Not for querying an already-deployed platform DP — use nxd-data-product-query for that.
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
  version: 0.9.1
---

# nxd-pocket-loop skill

## Overview

This skill drives the **Nexty Pocket loop**: a natural-language intent plus a
local data source become a running, queryable data product on a local desktop
supervisor — no Kubernetes, no remote warehouse. The loop is:

```
intent + source + questions
   → infer the semantic model        (nxd-semantic-data-product)
   → generate the runnable closure    (nxd-generate-dp)
   → boot + serve on the supervisor   (nxd-desktop-supervisor serve)
   → translate NL question → query    (this skill, agent-side)
   → answer, and refine wrong answers back into a regenerate
```

This skill is the **orchestrator**. It does not re-teach inference or code
generation — it invokes the skills that own those, then drives the supervisor
CLI to run and query the result.

> **You own the loop, not the gates.** This skill sequences the work loosely and
> narrates progress. It does NOT enforce ordered approval gates or autonomy
> budgets — that hardening lives supervisor-side and is deferred. Keep one data
> product in flight at a time while iterating.

## Preflight — check before you start

Before the loop, confirm the environment is ready and stop with a clear message
if not:

- **`nxd-desktop-supervisor` is on `PATH`** (`command -v nxd-desktop-supervisor`).
  If absent, point the user at the local-desktop provisioning step
  (`nxd-desktop-setup.sh` — it builds the two binaries onto `PATH` and provisions
  the Python runtime). Do **not** try to `cargo build` or `uv sync` inline
  yourself; that is the provisioning step's job. Do not proceed until it resolves.
- **The `nxd-desktop-kernel-host` sibling binary is present too.** The supervisor
  resolves `nxd-desktop-kernel-host` from the SAME directory as its own
  executable at boot and hard-fails without it. Verify both sit together, e.g.
  `command -v nxd-desktop-kernel-host` resolves to the same directory as the
  supervisor. If only the supervisor is on `PATH`, the runtime is half-installed —
  re-run the provisioning step.
- **The source directory has the expected shape** — a CSV connector export: one
  subdirectory per table, `*.csv` inside. If the shape is wrong, ask.
- **A writable data directory** for the supervisor's state and generations
  (`--data-dir`).
- **The Python runtime is provisioned and `NXD_DESKTOP_PYTHON` points at it.**
  The supervisor does NOT prepare a venv — it only *resolves* an interpreter
  (`NXD_DESKTOP_PYTHON`, else a dev venv next to the binary, else `python3`). If
  the provisioning step set `NXD_DESKTOP_PYTHON`, confirm the export reached your
  shell (see below); if it silently falls back to an interpreter with no nxd
  wheels, the transform fails at import.
- **Your shell has the provisioning step's `export` lines.** In some agent
  sandboxes each `Bash` call is an independent process, so a `PATH` /
  `NXD_DESKTOP_PYTHON` export set in one call may NOT be visible in the next.
  Re-check `command -v nxd-desktop-supervisor` and `echo "$NXD_DESKTOP_PYTHON"`
  at the **start of the run**, and if they don't persist, prefix each supervisor
  command with the exports (`PATH="…:$PATH" NXD_DESKTOP_PYTHON="…" nxd-desktop-supervisor …`)
  the same way the bearer is passed per-command below.

## What you drive — the supervisor CLI contract

The local supervisor is the `nxd-desktop-supervisor` binary. Each subcommand
prints one machine-readable document on stdout (diagnostics go to stderr).

- **serve** — pin a generated closure, boot the kernel, run the transform,
  publish, and keep the semantic query endpoint alive as a background process.
  ```
  nxd-desktop-supervisor serve --definition <closure-dir> --workflow <id> --data-dir <dir>
  ```
  Prints `KEY=VALUE` lines: `run_id=…`, `artifact_id=…`, `definition_id=…`,
  `semantic_endpoint=http://127.0.0.1:PORT/mcp/`, `semantic_child_pid=…`,
  `supervisor_pid=…`, `published=yes` on **stdout**. **`bearer_token=…` is printed
  to stderr, not stdout** (kept off stdout so it doesn't leak into captured
  output) — so capture BOTH streams (e.g. `serve … > out.txt 2> err.txt`, or
  redirect `2>&1`) and read the bearer from stderr, or you will have an endpoint
  with no token. The endpoint stays alive across separate `query`/`describe`
  calls until you `stop` it. Re-running `serve` on the SAME `--workflow` replaces
  the DP cleanly and rebinds the same endpoint — the regenerate primitive.
  (`create --hold-secs N` is a smoke variant whose endpoint lives only N seconds
  and dies on return; use `serve` for the loop.)

- **describe** — introspect the running DP's semantic catalog.
  ```
  nxd-desktop-supervisor describe --endpoint <ep>
  ```
  Reads the bearer from `NXD_DESKTOP_BEARER`. Prints the models with their
  measures and dimensions — the canonical concept names to query by. This is how
  you learn what to select; do not guess concept names.

- **query** — run a governed semantic query against the running DP.
  ```
  nxd-desktop-supervisor query --endpoint <ep> --measure <m> [--dimension <d> …]
  # or, for filters / ordering / limit:
  nxd-desktop-supervisor query --endpoint <ep> --selection <file.json>
  ```
  Reads the bearer from `NXD_DESKTOP_BEARER`. Prints ONE JSON line:
  `{"columns": [...], "rows": [...], "compiled_sql": "...", "row_count": N,
  "truncated": bool}`. `--measure`/`--dimension` are sugar for the simple case;
  `--selection <file>` takes a JSON document `{measures, dimensions, filters,
  order_by, limit}` for anything richer. The query is by **measure and dimension
  names** — never raw SQL, never natural language.

- **status** — check what is published for a workflow.
  ```
  nxd-desktop-supervisor status --data-dir <dir> --workflow <id>
  ```
  Prints `current_artifact=<id|none>`, `pointer=<id|none>`.

- **stop** — tear down a served endpoint and its semantic child.
  ```
  nxd-desktop-supervisor stop --data-dir <dir>
  ```
  Run this when the loop is done, or before re-serving a fresh workflow.

## The loop — step by step

### Step 1 — Gather intent, source, and questions

Establish three things (ask the user for whatever is missing):

- **Intent** — what the data product is about, in the user's words.
- **Source** — where the local data lives (the CSV export directory checked in
  preflight).
- **Questions** — the natural-language questions the DP must answer. These drive
  the whole inference (right-to-left): the model is judged by whether it answers
  them.

Warm the user up before long work: state that you'll infer a model, generate the
DP, run it locally, and then answer their questions — so a multi-minute build is
expected, not a stall.

### Step 2 — Infer the semantic model

Invoke the **nxd-semantic-data-product** skill in its inference mode: profile the
local source into `schema.json`, then derive the semantic model (grains,
dimensions, metrics, joins, PII) from the profile **and** the user's questions.
That skill owns the role grammar and the `__nxd_semantic__` annotations — follow
it; do not duplicate its guidance here.

### Step 3 — Generate the runnable closure

Invoke the **nxd-generate-dp** skill: assemble the complete runnable closure —
`spec.py`, `models.py`, `transform/main.py`, `requirements.txt`, and the
`deployment-spec.yaml` / `manifest.yaml` / `models.yaml` wiring — from the intent,
the inferred model, and the connector config. That skill owns the local DP shape
(DuckDB output port, dlt-in-transform, local executor) and the naming invariant.
The output is a **closure directory** — the `--definition` argument for Step 4.

### Step 4 — Serve on the supervisor

Serve the closure (a persistent endpoint the loop can query repeatedly):

```
nxd-desktop-supervisor serve --definition <closure-dir> --workflow <id> --data-dir <dir>
```

Fail closed unless the command SUCCEEDS (exit 0) and every required key is present
and non-empty — in particular `published=yes`. Capture `semantic_endpoint` and
`supervisor_pid` from **stdout**, and `bearer_token` from **stderr** (redirect
both — e.g. `serve … > out.txt 2> err.txt` — since the bearer is deliberately not
on stdout). Pass the bearer to each subsequent call **per command**, not via a
persistent `export` (a separate agent shell may not inherit it):

```
NXD_DESKTOP_BEARER="<bearer_token>" nxd-desktop-supervisor describe --endpoint <ep>
```

Keep the token out of narration. Confirm the publish before querying:

```
nxd-desktop-supervisor status --data-dir <dir> --workflow <id>
```

`current_artifact` must be non-`none`. Narrate: report that the DP built,
published, and is serving, and that you're about to query it.

### Step 5 — Answer the questions (NL → governed query)

The query surface is **structured** (measure/dimension names); the
natural-language translation is yours to do. For each question:

1. **Discover the catalog.** Run `describe --endpoint <ep>` to see the running
   DP's actual measures and dimensions. The declared vocabulary is canonical —
   map against it, do not guess concept names from the source columns.
2. **Map the NL question to a selection.** Pick the measure(s) and dimension(s)
   that answer it — reuse the question→concept mapping approach from
   **nxd-data-product-query**'s semantic-layer section. Before running, restate
   the selection you chose and, if the question is ambiguous against the declared
   concepts, ask rather than silently picking.
3. **Check the question fits the grammar.** The query supports measures grouped
   by dimensions, plus filters / order_by / limit via `--selection`. It does NOT
   express raw-row retrieval or anything outside measures+dimensions(+filters).
   If a question needs something the grammar can't express (e.g. a per-row dump),
   say so and clarify — do not silently drop a constraint like "in Spain last
   month" and answer a broader total.
4. **Run the query** (`--measure`/`--dimension`, or `--selection <file>` for
   filters/ordering/limit), reading the bearer per-command from
   `NXD_DESKTOP_BEARER`.
5. **Parse + present.** Read the `{columns, rows, compiled_sql, row_count,
   truncated}` JSON. Render the answer as a compact table, state the concept
   selection that produced it, and if `truncated` is true label the result a
   partial preview — never present a truncated or unverified result as the
   complete answer.

### Step 6 — Refine wrong answers back into the loop

If an answer is wrong, missing, or unsatisfying, decide where the fix belongs and
keep BOTH levels bounded:

- **Query-level** (cheapest) — the model is right but the selection was wrong or a
  dimension was missing. Re-`describe`, re-map, re-`query`. Cap at ~2 remaps per
  question.
- **Model / DP-level** — the inferred model is wrong (missing metric, wrong grain,
  missing join, wrong PII). Go back to Step 2/3 to regenerate, then re-`serve` on
  the **same** `--workflow`. Cap at ~3 regenerate cycles total.

**After every re-serve, refresh:** re-read the new `semantic_endpoint` +
`bearer_token` from the serve output (they may change), re-confirm `status`, and
re-`describe` the catalog before mapping again — the regenerated model is exactly
when the catalog can differ. Define success as a catalog-grounded answer the user
accepts. If the loop doesn't converge within the caps, `stop` the endpoint and
report what you tried, what the DP currently declares, and where the gap is — do
not loop indefinitely or give up silently.

## Narration discipline (always)

- **Warm up** before any multi-minute step (inference, generation, serve).
- **Per-step progress** — report entering each phase; never a silent stall.
- **Label previews as previews.** A sampled, partial, or `truncated` result is a
  preview, not a verified answer — say so. Never present an unvalidated
  intermediate as the final answer.
- **Show the query behind the answer** — every answer states the
  measure/dimension selection that produced it.

## Turnkey client config (thin)

To wire one client (Claude Desktop / Cowork / Claude Code) to a running DP, write
that client's MCP config pointing at the running DP's `semantic_endpoint` as the
MCP server URL, with `Authorization: Bearer <bearer_token>` as its auth header —
using the client's own config schema and file location (these differ per client;
do not assume one shape). Never print the bearer token into the chat. This is the
one turnkey path for the single client you iterate on — keep it minimal.

## Invariants — never violate these

- **Do not re-teach inference or code generation.** Invoke
  nxd-semantic-data-product and nxd-generate-dp.
- **Query is by measure/dimension name, not raw SQL or NL.** The NL→selection
  translation is agent-side; ground it in `describe`.
- **Serve, don't hold.** Use `serve` for the loop's persistent endpoint; `stop`
  it when done. `create --hold-secs` is a smoke variant only.
- **One workflow id per data product.** Re-`serve` the same id to regenerate.
- **The supervisor data dir is off-limits.** Everything under `.pocket/state/`
  — pinned snapshots in `definitions/<id>/`, `state.sqlite*`, `staging/` — is
  immutable supervisor-owned state. Never `chmod`, edit, or hand-write those
  files to fix a closure. A concrete `.../staging/run-<id>/data.duckdb` path
  inside a pinned `manifest.yaml` is the supervisor's own resolved runtime path,
  not a defect. If a served closure is wrong, fix it in **your** source dir and
  re-`serve` — the supervisor re-pins a fresh snapshot.
- **Bearer per command, never `export`.** Keep it out of narration.
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
