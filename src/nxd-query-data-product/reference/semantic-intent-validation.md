# Semantic query: intent validation

*Reference for Step 6f of the `nxd-query-data-product` skill. What the intent gate
does and why, covering only what the skill validates today. Design background, the
MCP tool-generation mechanics, and product-side follow-ups live in the skill
[README](../README.md).*

## The two-layer trust model

A natural-language analytics question travels through two independent steps:

```
question ──(intent→selection)──► selection ──(selection→SQL)──► SQL ──► result
            "did we understand?"   {measures,    "did we compile     governed
                                    dimensions,    it faithfully?"     rows
                                    filters}
```

| Layer | Question it answers | Status in NXD |
|---|---|---|
| **selection → SQL** | Did we compile the selection faithfully (right joins, no fan-out)? | **Solved & deterministic.** The `nxd.experimental.semantic` compiler enforces a single grain per query (chasm-trap guard) and renders read-only aggregated SQL. Same selection → same SQL. |
| **intent → selection** | Did the selection capture what the user actually meant? | **The open layer.** A *valid* selection can still be the *wrong* one: `call_count` when the user meant `sales_calls`, a missing filter, the wrong time boundary. It compiles clean, runs governed, returns a confident number — for the wrong question. |

**The determinism dividend:** because the lower layer is deterministic, *once the
selection is right, the number is right — forever and reproducibly*. So all the
residual trust risk collapses onto the upper layer. That is where NXD has an edge
the SQL-first world lacks: **the selection is a first-class, inspectable object**
(`{measures, dimensions, filters}` on the wire), not buried inside generated SQL.
We can validate it as its own artifact, echo it back, and confirm it — none of
which free-form text-to-SQL can do.

The intent gate (Step 6f) validates that upper layer **client-side**, using only
what the three semantic tools (`list_models`, `describe_model`,
`run_semantic_query`) already return.

## The three techniques

The gate runs three checks against the selection before executing. All read only
`describe_model` metadata — no extra server surface.

| Technique | What it does | How it reads the catalog |
|---|---|---|
| **Round-trip echo** | Restate the resolved selection in plain language from the catalog descriptions and show it before executing. Catches mis-mapping the user can see. | Pure assembly from each metric's / dimension's `description`. Deterministic — same selection → same echo. |
| **Catalog-aware critic** | An LLM check: given the question + selection + catalog descriptions, does this selection answer the question? Produces the verdict (`ok` / `ambiguous` / `likely-wrong`) that drives clarify. | Reads metric/dimension `description`s; checks each dimension is in the metric's `compatible_dimensions` or a join's `reaches_dimensions`. |
| **Clarification on ambiguity** | When the verdict is unclear or a concept doesn't fit, ask the user with the real candidate concepts instead of guessing. Abstain beats a confident wrong answer. | `AskUserQuestion` listing the actual concepts from `list_models` / `describe_model`. |

### Why these run client-side

Echo is **deterministic** — a pure function of the selection and the catalog
metadata — so it renders client-side for free. The critic and the clarify decision
are **non-deterministic / interactive**, so they stay client-side too: keeping them
out of the compiler preserves the determinism dividend (the `run_semantic_query`
path stays "same selection → same SQL"). None of the three needs anything beyond
what `list_models` + `describe_model` already return.

## End-to-end flow (Step 6f)

```
list_models → describe_model(name)      ← discover catalog: metrics (w/ compatible_dimensions),
        │                                   dimensions (w/ pii), joins (w/ reaches_dimensions)
build selection {measures, dimensions, filters}   ← concept names only, never SQL
        │
┌──────────────── INTENT GATE (client-side) ────────────────┐
│  critic   {question, selection, describe_model} → verdict   │
│           + compatible_dimensions / reaches_dimensions chk  │
│  echo     restate selection in NL (+ PII note)              │
│  clarify  verdict ambiguous/wrong OR dim unreachable        │
│           → AskUserQuestion; abstain, do not execute        │
└─────────────────────────────────────────────────────────────┘
        │  critic ok / user confirmed
run_semantic_query           ← deterministic compile → governed exec → rows + compiled_sql
        │
on error → troubleshooting table (mixed-grain → one query per model, …)
```

## See also

- Step 6f in [`../SKILL.md`](../SKILL.md) — the operational steps.
- The skill [README](../README.md) — design rationale, MCP tool-generation
  mechanics, and the deferred / product-side follow-ups (self-consistency vote,
  value-linking).
