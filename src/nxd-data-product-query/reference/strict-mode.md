# Strict mode (MCP-only, plan-verified)

## Contents

- [Rules](#rules) — the five declarative constraints; per-query no-cache discipline
- [Discovering MCP functions — one multiplexer session](#discovering-mcp-functions--one-multiplexer-session) — `proxy__getDataProductsHealth` + one `tools/list`
- [Flow (one shape that satisfies the rules)](#flow-one-shape-that-satisfies-the-rules) — the five execution steps
- [Plan format (shape on disk)](#plan-format-shape-on-disk) — JSON schema the validator reads
- [Plan Validation](#plan-validation) — independent validator, five checks, retry loop, known limitation
- [Abstain rules](#abstain-rules) — when strict mode hard-fails
- [Output the user sees](#output-the-user-sees) — three-part response shape

---

A locked-down mode for queries that must demonstrably go through MCP and nothing else. The rules below are declarative — satisfy them however the flow works out per request; do not treat the list as execution order.

## Rules

1. **Data access only via MCP endpoints exposed by Data Products.** Do not authenticate against or call any underlying data source directly (no Snowflake/Postgres/pgvector dial, no presigned-URL fetch, no external API call). Discover available DP MCP endpoints through the **mesh-level MCP gateway** — a per-mesh endpoint that lists every DP MCP server registered on the mesh and the functions each exposes. Resolve its URL from the mesh config the same way Step 1 of the parent skill resolves the api/app host (see `mcp_gateway.py`).
2. **Semantic relationships only via the `semantic_model` MCP endpoints.** Some DPs expose a `semantic_model` MCP function that returns model attributes plus typed relationships to models in **other** DPs (foreign keys, derived-from, joins-on). For any cross-DP reasoning use **only** these endpoints; never infer relationships from column-name heuristics, embedding-space similarity, or memory.

> **Only `semantic_model` is standard.** Every other MCP tool name on a DP — search, get, scan, top-k, custom RPCs — is author-defined and may change. The skill must learn every non-`semantic_model` tool from a **live** gateway call, never from a hard-coded list, doc reference, or prior run.

> **Re-fetch every query.** The set of DPs, their MCP endpoints, and the tools each one publishes can change at any time (new DP launched, schema rev, breaker flips, redeploy). Run `mcp_gateway.py` and `semantic_relations.py` again **for every user query** — do not reuse a catalogue from an earlier conversation, an earlier turn, or any on-disk cache older than the current question. If a previous file is on disk, delete it or overwrite it; the catalogue is **query-scoped** — fresh per question, discarded after the response.

3. **Plan-first, human-readable.** Process every user question by first building a written **query plan** that covers the full execution — including multi-DP / multi-endpoint paths — and the **provenance** of each step: which MCP function the step calls, which `semantic_model` response justified each join / projection / filter, and which user-question phrase mapped onto each parameter. The plan is text the user can read end-to-end before anything runs.
4. **Validated before execution.** Every plan goes through an independent **plan validator** that checks (a) every relationship asserted in the plan is present in at least one `semantic_model` MCP response collected this session, (b) every data-fetching step targets an MCP endpoint listed by the gateway, and (c) no step calls a non-MCP path (raw SQL against a port, direct presigned-URL fetch, direct HTTP to an external API).
5. **Execute only if validation passes.** On pass: run the plan via MCP calls and return `{plan, validation_report, results}` to the user. On fail: return the plan, the validation failures, and a short explanation — **do not run any step**.

## Discovering MCP functions — one multiplexer session

The mesh runs a single **MCP multiplexer** (mcp-proxy-api) at `<base>/dp/mcp/`
(or `<base>/mcp/`). One MCP session yields BOTH the per-DP health rollup and
every DP's tool list — no `nxd mcp health` CLI subprocess, no per-DP `tools/list`
fan-out. `scripts/mcp_gateway.py` does it all in one `initialize` + two
`tools/call`/`tools/list`, re-run **every query, no cache**:

- **Health** — calls the multiplexer's `proxy__getDataProductsHealth` tool for
  per-DP `derived_state` / breaker (this replaces the old Stage-1
  `nxd mcp health` subprocess — and with it the `--mesh` foot-gun: there is no
  CLI mesh selection anymore; the multiplexer URL is derived from the active
  mesh's `api_url`).
- **Tools** — one `tools/list` on the multiplexer returns every DP's tools,
  namespaced `<function>__<hash>` (the gateway's per-DP namespace). This replaces
  the Stage-2 per-endpoint fan-out.

```bash
python3 scripts/mcp_gateway.py --token-file /tmp/strict-tok.txt --out /tmp/strict-gw.json
```

`mcp_gateway.py` groups the namespaced tools by their `__<hash>` (the opaque
per-DP key the multiplexer assigns) and writes the catalogue JSON with
`endpoints[*].{endpoint, dp_full_name (= hash), tools[*].{name, description,
input_schema}}` plus a flat `function_index` of `(hash, wire_name)` pairs and the
multiplexer's own `gateway_tools`. Every `endpoints[*].endpoint` IS the
multiplexer URL, so a caller dials it with the namespaced wire name
(`semantic_relations.py` / `mcp_call.py` work against it unchanged).

> **hash, not fullName.** The multiplexer namespaces tools by an opaque
> `__<hash>`, not the DP fullName. The hash is a stable per-DP key *within a
> session* — enough for the validator (which matches `(dp, tool)` pairs from this
> same catalogue). To map hash→fullName for the user, call
> `gateway_tools.py details --dp <fullName>` or read the group's `semantic_model`
> response (it carries its own `data_product`).

Auth: a **PAT** (`nxdpat_…`, from `nxd mcp config` / `nxd login`) on the
**`X-Nextdata-Token`** header — the documented MCP auth. `mcp_http.py` picks the
header by token type automatically (PAT → `X-Nextdata-Token`; OAuth session token
→ `Authorization: Bearer`); the two are mutually exclusive on the gateway.

**What the catalogue gives you, by function class:**

| Class | How to identify it in the catalogue | What it returns | Use it for |
|---|---|---|---|
| **(a) Data-returning functions** | Any tool whose base name (before `__<hash>`) does **not** match `^semantic[_-]?models?$` — search/get/scan/top-k/custom RPCs the DP author defined | Domain data (rows, ranked chunks, aggregates, summaries). Shape is whatever the DP author published | Plan steps that fetch data |
| **(b) Semantic-model functions** | Tool whose base name matches `^semantic[_-]?models?$` (wire name `semantic_model__<hash>`) | The serialized cross-DP registry payload — models (grain + owning data_product + physical DB.SCHEMA.TABLE), dimensions, metrics, and joins (`left`/`right`/`on`/`cardinality`) to models in **other** DPs | Plan Validation Rule 2 / Rule 4 — every cross-DP join / projection / filter must trace back to an entry returned here. Run via `scripts/semantic_relations.py` |

Only the **(b)** name is standard. Everything in **(a)** is author-defined and may change between runs — that is why discovery is re-fetched per query.

## Flow (one shape that satisfies the rules)

1. **Discover MCP surface.** Call the mesh MCP gateway to enumerate DP MCP endpoints and their declared functions. Reuse this catalogue **only within the current query run** — never across queries (see Rule 3 above). The next user question must start with a fresh `mcp_gateway.py` invocation.
   ```bash
   python3 scripts/mcp_gateway.py --token-file /tmp/strict-tok.txt --out /tmp/nxd-mcp-gateway.json
   ```
2. **Collect semantic models.** For each candidate DP that exposes a `semantic_model` MCP function, call it and collect the returned model attributes + cross-DP relationships into a single relations bundle. Candidates are the DPs whose descriptions / function names plausibly relate to the user's question — narrow by domain when there are many.
   ```bash
   python3 scripts/semantic_relations.py --gateway /tmp/nxd-mcp-gateway.json --token-file /tmp/strict-tok.txt --out /tmp/nxd-relations.json
   ```
   (Optional `--dps <fullName>,<fullName>,…` filter when only specific DPs are relevant.)
3. **Draft the plan (LLM, in the conversation).** Using the gateway + relations bundle, write a human-readable plan with these sections:
   - **Question** — the user's question, verbatim.
   - **Candidate sources** — which DP MCP endpoints are relevant and why (one line each, citing the gateway entry / `semantic_model` response that justified inclusion).
   - **Steps** — ordered execution steps. Each step lists: DP `fullName`, MCP function name, request payload, expected response shape, and which relations bundle entry (if any) justified the join/projection/filter.
   - **Joins & relationships** — every cross-DP join or relationship the plan relies on, with a pointer to the `semantic_model` MCP response (DP + path) that declares it.
   - **Provenance** — for each step, which phrase of the user question mapped onto which parameter.
   - **Open questions / assumptions** — anything the relations bundle didn't fully cover.
4. **Validate the plan.** Run the validator over the plan + the gateway + relations bundle pulled for **this** query (steps 1-2):
   ```bash
   python3 scripts/plan_validator.py --plan /tmp/nxd-plan.json --gateway /tmp/nxd-mcp-gateway.json --relations /tmp/nxd-relations.json --out /tmp/nxd-validation.json
   ```
   The validator emits `{passed: bool, checks: [...], failures: [...]}`. Failures categorise as `unknown_relationship`, `non_mcp_step`, `unknown_endpoint`, `unknown_function`, `unsupported_param`.
5. **Execute or abstain.**
   - If `passed=true`: walk the plan and run each step via `scripts/mcp_call.py` (a thin CLI over `mcp_http.call_tool_one_shot` — see below). Collect responses and return `{plan, validation_report, results}` to the user.
     ```bash
     # Every endpoint in the catalogue IS the multiplexer URL; the tool is the
     # namespaced wire name `<function>__<hash>` from function_index.
     python3 scripts/mcp_call.py \
       --endpoint "$(jq -r '.endpoint' /tmp/nxd-mcp-gateway.json)" \
       --tool "<function>__<hash>" \
       --args '<json-from-step.request>' \
       --token-file /tmp/strict-tok.txt \
       --out /tmp/nxd-step-<id>.json
     ```
   - If `passed=false`: return `{plan, validation_report}` with each failure named and the rule it violated (Rule 1 / 2 / 4). **Stop.** Do not retry the underlying query through a non-MCP path; if the user wants to relax strict mode, they pass `--strict=false` (or "drop strict mode") and the skill falls back to the default Step-6 routing of the parent skill.

## Plan format (shape on disk)

`/tmp/nxd-plan.json`:

```json
{
  "question": "…verbatim user question…",
  "candidate_sources": [
    {"dp": "<fullName>", "mcp_function": "<fn>", "reason": "…", "evidence": {"gateway_entry": "…"}}
  ],
  "steps": [
    {
      "id": "s1",
      "dp": "<fullName>",
      "mcp_function": "<fn>",
      "request": {"…": "…"},
      "expected_response_shape": "…model name or schema ref…",
      "depends_on": [],
      "join_basis": null
    }
  ],
  "relationships_used": [
    {"from_dp": "<A>", "from_model": "<m1>", "to_dp": "<B>", "to_model": "<m2>", "kind": "fk|derived|joins_on", "evidence": {"semantic_model_dp": "<A>", "path": "relationships[0]"}}
  ],
  "provenance": [{"step_id": "s1", "param": "from", "phrase": "…", "source": "user_question"}],
  "assumptions": ["…"]
}
```

## Plan Validation

The validator runs **independently** of the plan generator. Treat plan generation and plan validation as two separate actors with separate inputs:

- **Generator inputs** — the user question, the gateway catalogue, the relations bundle, prior conversation context, scratch notes, embedding-space hunches, anything Claude reasoned through to pick steps. Generator emits the plan JSON; that JSON is the **only** thing the validator may consume from the generator.
- **Validator inputs** — the emitted plan JSON, and a *fresh* read of the gateway catalogue + relations bundle from disk. The validator must **not** read the generator's chain of thought, the prior turn's notes, any LLM reasoning, or anything else the generator used to build the plan. If a fact does not survive serialisation into the plan, it does not exist for the validator.
- **Same files, fresh load.** The validator opens `gateway.json` / `relations.json` itself rather than receiving them from the generator. This catches generator drift: a plan that referenced a tool the generator "remembered" but never wrote into the plan, or a relationship the generator inferred but never recorded under `relationships_used`, will fail validation here.

Concrete checks the validator runs:

- For every `relationships_used[*]`: an entry must exist in `relations.json` whose `from_dp/from_model/to_dp/to_model/kind` matches; the `evidence.semantic_model_dp` must be the DP that returned it.
- For every `steps[*]`: `dp + mcp_function` must appear in `gateway.json`'s function index.
- No step may carry a `direct_sql`, `presigned_url`, or `http_request` field — those tag non-MCP paths and fail the run.
- Every `steps[*].request` field must reference either (a) a literal from `provenance`, (b) the output of a `depends_on` step, or (c) a value drawn from `relationships_used`. Unbound params fail.

**Generator ↔ validator retry loop.** On `passed=false`, surface the structured `failures[]` back to the generator with each entry's `check`, `step_id`, and `detail`. The generator rewrites the plan to address the named gaps — add a missing `relationships_used[*]` and back it with a real `relations.json` entry, swap an unknown tool for one in the gateway, bind an unbound param, drop a non-MCP field — and the validator re-runs over the new plan. Cap the loop at **3 attempts** to bound cost.

**Hard fail if no valid plan is reachable.** If the generator cannot produce a plan that the validator passes within the retry cap, **the query fails**. Do not run any step. Return to the user: the final attempted plan, the validator's failure list from the last attempt, and a short explanation that points to whichever of these is the root cause: (a) the gateway catalogue has no tool that can answer the question, (b) `relations.json` lacks a relationship the question requires, (c) the question needs data not exposed by any reachable DP. Tell the user what would have to change on the mesh side (add a tool, publish a relationship in a `semantic_model` response, fix a Broken endpoint) for the same question to succeed next time.

**Known limitation — structural only.** Plan Validation verifies that declared relationships *exist* in `semantic_model` responses; it does **not** verify that the underlying values on the two sides of a relationship actually intersect at runtime. A `SameAs` between `A.x` and `B.y` can pass validation while every per-row fan-out returns zero because the identifier encodings diverge or the value sets are disjoint. Symptom during execution: per-row queries return empty / zero while the same tool called without that filter returns non-zero — that's the data-level mismatch fingerprint.

When that pattern appears in results, surface it explicitly to the user; do not retry with alternate encodings (that's hallucination). The fix lives on the mesh side: either correct the `semantic_model` link (e.g. `SameAs` → `Derived` with the actual transform), or fix one side's stored values. The skill may optionally implement a Rule-6 runtime probe that, before fan-out execution, samples N distinct values from each side of a relationship via the available data tools, intersects them, and abstains when the intersection is empty — this catches the class of bug at plan-time rather than after a fruitless execution. Implement only when the source DP exposes a tool that returns distinct values cheaply.

## Abstain rules

- Mesh MCP gateway not reachable → strict mode cannot run. Tell the user; do not silently fall through.
- No candidate DP exposes a `semantic_model` MCP function for the model the user is asking about → cross-DP reasoning is not possible in strict mode. Return the gateway + relations bundle gathered so far and stop.
- Plan needs a step that is not declared in any DP's MCP function list → validation fails with `unknown_function`; do not invent.

## Output the user sees

A single response with three parts, in order: the **plan** (human-readable, the text of the JSON above rendered as prose + a table of steps), the **validation report** (pass/fail + each check), and, if validation passed, the **results** (one block per step, with MCP function + response excerpt). If validation failed, the third part is replaced by an "Execution skipped" notice citing the rule numbers that were violated.
