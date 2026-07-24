# Task scheduling — routing, sequencing, caps, and fan-out

## Contents

- [Route the request before doing work](#route-the-request-before-doing-work)
- [Step order and dependency edges](#step-order-and-dependency-edges)
- [Bounded-loop caps](#bounded-loop-caps)
- [One data product in flight](#one-data-product-in-flight)
- [Subagent fan-out](#subagent-fan-out)

This is the **task-scheduling** half of the pocket loop: which path a request
takes, the order the steps run in, what forces a re-run, how many times the loop
may retry, and where independent work may run in parallel. The **context**
half — reattaching to a product across sessions, what persists, what dies — lives
in [context-and-resume.md](context-and-resume.md).

## Route the request before doing work

Classify the request before provisioning, generation, or querying. Prefer the
smallest path that can give an honest answer:

| Situation | Route |
|---|---|
| **Explicit deployed/platform product** — the user names a remote DP, cluster, or platform endpoint | Hand off to `nxd-data-product-query`. Do not create a local replacement. |
| **Existing local product** — the task supplies its `semantic_endpoint` and bearer token | Call `mcp__nxd-desktop__describe_models`, then answer through `mcp__nxd-desktop__run_semantic_query`. |
| **Existing local product, but no endpoint/token** — the typical new session, since the bearer is per-session and never persisted | **Reattach, don't rebuild.** Call `mcp__nxd-desktop__list_data_products`, then `mcp__nxd-desktop__resume_data_product` with the workflow id — a fresh endpoint and bearer in seconds, no regeneration. Rebuild is the fallback only when the published artifact is gone. Full playbook: [context-and-resume.md](context-and-resume.md). |
| **In-scope source data** — attached/exported CSVs, another local file (JSON/JSONL/Parquet), a connected workspace folder, pasted tabular data, a spreadsheet, an accessible live database connection, or an off-mesh REST API the user describes | Preserve the source, infer a model, generate a local closure when no suitable local product exists, then answer through the supervisor. An ordinary single file source may be copied unchanged into the generated closure's required export layout; a database or API source is described (host/URL, credentials-availability, table/endpoint list), never fabricated, and its connection details pass through to generation exactly as the user gave them. Never modify a supplied original. |
| **No product and no source** | Ask one concise question naming the missing thing: the local data file/folder or an existing product to query. Do not manufacture a dataset, create a throwaway database, or probe Cowork uploads/workspaces with Bash in hope of finding one. |
| **Trivial, non-durable calculation** — for example, arithmetic over values pasted in the request, with no request to analyze or reuse data | Answer directly. Do not start a supervisor or build a product. |
| **Local analysis requested but runtime unavailable** | Stop before fallback work. State that the local analysis runtime is unavailable, identify the missing MCP connection or host-local runtime prerequisite, and point to `nxd-desktop-setup.sh` / the Desktop connection repair. Do not substitute SQLite, raw SQL, pandas, or shell aggregation. |

Treat ambiguous requests conservatively. If a question could mean either a
one-off calculation or analysis of an unseen source, ask which data or product
should answer it. If data is in scope and the user asks for a recurring,
shareable, or multi-question analysis, prefer the reusable local-product path.

## Step order and dependency edges

The loop runs Steps 1–6 in `SKILL.md`. The order is not arbitrary — each step
consumes the previous step's artifact, so a change upstream forces the
downstream steps that depend on it to re-run:

```
gather (1)  → infer (2)      (questions + source shape drive the model)
infer (2)   → generate (3)   (the semantic model is placed into the closure)
generate(3) → build (4)      (the closure is the --definition the supervisor pins)
build (4)   → query (5)      (the served endpoint + catalog answer questions)
query (5)   → refine (6)     (a wrong answer routes back to 2/3 or stays in 5)
```

When a refine cycle (Step 6) changes an upstream artifact, re-run only the
downstream steps that actually depend on the change, and say which ones before
doing so:

- A **query-level** fix (wrong selection, missing dimension) re-runs Step 5 only.
- A **model/DP-level** fix (missing metric, wrong grain, a new derived model)
  re-runs Steps 2/3 → 4 → 5 with the **same** workflow id.

After any rebuild the catalog can differ, so Step 5 always re-`describe_models`
before mapping again — never map against a remembered catalog.

## Bounded-loop caps

The loop is bounded at both levels. Keep BOTH bounded and report
non-convergence rather than looping forever or giving up silently:

- **Query-level remap** (cheapest) — the model is right but the selection was
  wrong or a dimension was missing. Re-describe, re-map, re-query through MCP.
  Cap at **~2 remaps per question**.
- **Model / DP-level regenerate** — the inferred model is wrong, or the question
  needs a column/grain that does not exist yet (a filtered figure, a ratio, a
  monthly rollup, a classification). The latter is a **derived model**, not a
  query tweak: go back to Step 2/3, have `nxd-generate-dp` materialize the
  ruling, rebuild through MCP with the **same** workflow id. Cap at **~3
  regenerate cycles total**.

If the loop does not converge within the caps, report what you tried, what the
product currently declares, and where the gap is.

## One data product in flight

Keep **one data product in flight at a time** while iterating. This is not a
limit on how many *sources* one data product may have — a data product may draw
on several labeled sources — only on how many products you build or serve at
once.

The supervisor enforces the same shape from its side: a session serves **one
workflow at a time**. Building or resuming a *different* workflow replaces the
current endpoint, so any earlier endpoint from this session stops answering.
Resuming or rebuilding the **same** workflow id is the regenerate/reopen
primitive and returns the same product.

## Subagent fan-out

Independent, read-only work in the loop MAY be dispatched to parallel subagents
so their intermediate reads stay out of the main conversation. This is
**permitted, not required** — a single-source, single-question loop needs none
of it. Fan out only when the work is genuinely independent:

- **Step 2, multi-source profiling** — when a data product draws on several
  sources, each source's profile (`schema.json`) is independent. Profiling them
  concurrently keeps each source's sample reads out of the main thread. Carry
  every source's label forward on the model it produces, exactly as the
  single-thread path would.
- **Step 5, multi-question answering** — independent questions that map to
  their own selections can be answered concurrently against the **already-served**
  endpoint. Each subagent runs `describe_models` + `run_semantic_query` against
  the same endpoint/bearer and returns its rows; the main thread presents them.

Two hard boundaries on fan-out:

- **Build/serve (Step 4) is single-flight and stays on the main thread.** The
  supervisor serves one workflow at a time; concurrent builds would fight over
  the runtime lock and replace each other's endpoints. Never fan out a build.
- **Every subagent inherits the invariants** — no raw SQL / pandas / shell
  aggregation fallback, describe before mapping, label previews as previews. A
  subagent that cannot answer through the governed query returns that, it does
  not reach for a fallback.
