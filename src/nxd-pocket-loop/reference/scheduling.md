# Task scheduling — routing, sequencing, caps, and fan-out

## Contents

- [Route the request before doing work](#route-the-request-before-doing-work)
- [Step order and dependency edges](#step-order-and-dependency-edges)
- [Bounded-loop caps](#bounded-loop-caps)
- [One data product in flight](#one-data-product-in-flight)
- [Subagent fan-out](#subagent-fan-out)
- [Offloading generation to a subagent](#offloading-generation-to-a-subagent)

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
| **Share / hand off a product** — the user wants to give it to another person or machine | Call `mcp__nxd-desktop__export_data_product` with the same `definition` path used to build it. Read-only and on demand — not part of the build/query loop. It zips the closure, strips credentials fail-closed, and emits a guided `IMPORT.md` for the recipient to rebuild. Full playbook: [handoff-export.md](handoff-export.md). |
| **In-scope source data** — attached/exported CSVs, another local file (JSON/JSONL/Parquet), a connected workspace folder, pasted tabular data, a spreadsheet, an accessible live database connection, or an off-mesh REST API the user describes | Preserve the source, infer a model, generate a local closure when no suitable local product exists, then answer through the supervisor. An ordinary single file source may be copied unchanged into the generated closure's required export layout; a database or API source is described (host/URL, credentials-availability, table/endpoint list), never fabricated, and its connection details pass through to generation exactly as the user gave them — **except a live credential, which never enters an offloaded generate subagent (see the credential boundary under "Offloading generation to a subagent"); it is injected host-side**. Never modify a supplied original. |
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

## Offloading generation to a subagent

Profiling (Step 2) and code generation (Step 3) are the loop's heaviest context
consumers: source sample reads, model inference, and authoring `spec.py` /
`models.py` / `transform/main.py` / `CONTEXT.md`. None of that touches the
supervisor — it is pure file authoring against a durable closure directory — so
it MAY run in an isolated subagent whose intermediate reads never enter the main
conversation. The main thread keeps the things it alone can do: the **policy
read-back user turn**, the **single-flight build**, and the host-side path
verification and credential injection that precede that build.

This is **permitted, not required.** A single-source, single-question loop with
no supplied procedure should author in the main thread — the dispatch, the
structured hand-back, and the host-side path re-verification cost more than the
context a trivial closure would have spent. Reach for it when generation would
otherwise dominate the main context: multiple sources, a procedure-bearing
closure, or a long codegen.

**Split the dispatch at the inference/authoring seam — do not fan out Steps 2–3
as one unit.** A gap discovered after generation would otherwise re-run the
expensive profiling on every bounce:

1. **Profile subagent (Step 2, read-only).** Runs `nxd-semantic-data-product`
   inference: profiles each source into `schema.json`, derives the semantic
   model, and — crucially — surfaces any way the source data makes the user's
   supplied procedure ambiguous or under-determined. It returns the inferred
   model, the per-source schemas (each with its label), and a `gap_found` field
   naming any policy gap the profile exposed. It writes no closure and asks the
   user nothing. A **file** source (CSV/JSON/JSONL/Parquet) profiles freely here;
   a **live database/API** source is profiled on the main thread or from the
   user's description only (table/endpoint list, sample shape) — never fan out a
   profile that would need a live credential to connect (same credential boundary
   as generation, below).
2. **Main thread: the policy read-back.** With the profile in hand, run the
   Step 1a read-back for any result-changing gap — including one the profile
   surfaced — and wait for the user's approval. This user turn is the
   orchestrator's; it never happens inside a subagent.
3. **Generate subagent (Step 3).** Receives the already-computed model and the
   **verbatim approved policy** — never re-profiles, never re-opens the gate as a
   user turn. It authors the closure and runs the self-check. If it finds a
   result-changing gap the approved policy does not resolve — either a policy
   element the enumeration never covered, or a profiling finding that makes an
   approved element ambiguous or conditional — it stops and returns `gap_found`
   rather than guessing; the main thread does a fresh read-back and re-dispatches
   **generation only**, against the **same** workflow id and closure directory.

Scope each subagent's context to the work at hand: the dispatch names the
connector type(s) in play so the generate subagent loads only the matching
`nxd-generate-dp` connector references (a CSV closure needs none of
`database-source.md` / `api-source.md`), and the profile subagent loads only
`nxd-semantic-data-product`'s inference path. The heavy references then load in
the subagent that needs them and never in the main thread — the whole reason to
offload the step rather than run it inline.

Because the generate subagent hands back a record instead of leaving its work in
the main thread's context, that record must carry everything the main thread
needs to narrate honestly and build **without re-reading the closure** (re-reading
would re-inflate the context this split exists to save). Its return is
**structured, not prose**:

- `closure_path` **plus a surface tag** (`host_absolute` or `workspace_relative`)
  — a subagent writes to its own session surface and cannot itself guarantee the
  host sees that path;
- `promised_models` (base + derived names) so the main thread can state grain
  without opening `spec.py`;
- `policy_fingerprint` — the bands / anchors / precedence **as encoded** — so the
  main thread can confirm what shipped matches what the user approved;
- `self_check` as fields, not prose: Phase-C / Phase-D pass·fail, the transform
  dry-run result, and the `distributions` / `unverified` / `absent` read-back
  arrays verbatim (relay them unchanged — do not re-summarize; `UNIFORM` still
  means a value you supplied, not one the data produced);
- `credential_slots` for a db/API source — the credential **key names only**,
  never a value (see the credential boundary below);
- `gap_found` (or null) as a first-class field distinct from success.

**The main thread verifies before it builds.** Never pass a subagent-returned
path to `build_data_product` unverified: confirm the path resolves on the
supervisor's **host** surface and that `spec.py`, `models.py`,
`infra-profile.yaml`, `transform/main.py`, `requirements.txt`, `CONTEXT.md`, the
connector companion artifact (a file source's `data/` export, or the db/API
mapping file) — and, for a credentialed source, `SENSITIVE` and `.gitignore` —
all exist under it. `infra-profile.yaml` matters most: it is the file host-side
credential injection writes into, so a closure missing it passes a naive check
and then fails the build. A path that does not resolve host-side, or is missing a
required file, is a handoff failure, not a build input.

**Credential boundary — a live credential never enters a subagent.** For a
database or REST API source the closure carries a real credential in
`infra-profile.yaml`. Handing that value to a subagent in its prompt would copy a
secret into a second transcript — a new leak the main-thread flow does not have.
So the generate subagent writes a **placeholder** for the credential and returns
`credential_slots` (the key names); the real value is written into
`infra-profile.yaml` **host-side after the hand-back and before the build**, where
`SENSITIVE` / `.gitignore` / `chmod 0600` are asserted. A subagent must never
receive, echo, or narrate a live credential. When post-hand-back injection is not
available, keep credentialed generation on the main thread and fan out only
file-source (CSV/JSON/JSONL/Parquet) generation — those carry `attributes: []`
and have no secret to leak. A db/API dry-run therefore reports **not run** from
the subagent — expected, not a defect, because it holds no credential. The live
connectivity check runs host-side after injection **instead, and must run
there** — a `not_run` after injection is a real gap, not the subagent's benign
one.
