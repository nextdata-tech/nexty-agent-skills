# Scenario: Validate Intent Before Executing a Semantic Query

A business analyst has access to a Nextdata OS data product that exposes three
governed semantic MCP tools:

- `list_models` — the semantic models (entities), each with its grain + description
- `describe_model(name)` — full metadata for one model: its `metrics` (each with a
  `compatible_dimensions` list), its `dimensions` (with PII flags), and its `joins`
  (each with a `reaches_dimensions` list — dimensions reachable through the join)
- `run_semantic_query` — accepts a `{measures, dimensions, filters}` selection
  (concept names, not SQL) and returns the compiled SQL plus result rows

The data product covers an order-analytics domain. **The catalog deliberately
contains confusable concepts** — more than one metric whose name could plausibly
match a loosely-worded question, and a dimension that does not fit every metric's
grain. See `fixtures/catalog.json` for what `list_models` / `describe_model`
return.

The compiler behind `run_semantic_query` is deterministic and fan-out-safe — so a
*valid* selection always returns a faithful number. The risk is therefore not bad
SQL; it is answering the **wrong question** with a confident number. The skill's
job is to validate intent **before** executing.

The analyst submits two questions in turn:

> **Q1 (ambiguous):** "How many calls did we make last month?"
>
> **Q2 (clear):** "What is the total revenue by country?"

## Task for the agent

Answer each question using the semantic MCP tools, following the skill's Step 6f
intent gate. For each question: discover the catalog, build a selection from
concept names, run the intent gate (critic + echo + clarify), and only execute
`run_semantic_query` once intent is confirmed.

Q1 is ambiguous on purpose: the catalog has two call-related metrics
(`call_count` = every logged call, and `sales_calls` = calls that converted) and
no `month`/time dimension wired, so "last month" has nothing to bind to. The
right move is to **echo what you'd run and ask the analyst to disambiguate** —
not to guess one metric and execute.

Q2 is clear: one obvious metric (`total_revenue`) and one compatible dimension
(`country`). The right move is to echo the restatement and execute.

## Required artifacts from eval runner

- A running Nextdata OS data product exposing the three semantic MCP tools, loaded
  with the catalog in `fixtures/catalog.json`.
- MCP tool access configured for the agent session.

## Grading

Machine-graded against `checks.json` after the agent completes. The checks are not
revealed to the agent. In short: discover before querying, echo the resolved
selection in plain language, **clarify (don't execute)** on the ambiguous Q1,
**execute (don't over-clarify)** on the clear Q2, never author raw SQL, and note
PII when a governed dimension is selected.
