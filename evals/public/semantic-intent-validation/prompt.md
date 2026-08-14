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
match a loosely-worded question, a dimension that does not fit every metric's
grain, and a **decoy model with a misleading name** (`partner_directory`,
which sounds like a reference/lookup table, not a metrics model) that is the
only model carrying `partner_sourced_revenue`. See `fixtures/catalog.json` for
what `list_models` / `describe_model` return.

The compiler behind `run_semantic_query` is deterministic and fan-out-safe — so a
*valid* selection always returns a faithful number. The risk is therefore not bad
SQL; it is answering the **wrong question** with a confident number. The skill's
job is to validate intent **before** executing.

The analyst submits three questions in turn:

> **Q1 (ambiguous):** "How many calls did we make last month?"
>
> **Q2 (clear):** "What is the total revenue by country?"
>
> **Q3 (clear, but metric on the decoy):** "How much revenue did partners bring in?"

## Task for the agent

Answer each question using the semantic MCP tools, following the skill's Step 6f
intent gate. For each question: discover the catalog (calling `describe_model` on
**every** model `list_models` returns — do not skip a model because its name or
grain sounds irrelevant), build a selection from concept names, run the intent
gate (coverage + critic + echo + clarify), and only execute `run_semantic_query`
once intent is confirmed.

Q1 is ambiguous on purpose: the catalog has two call-related metrics
(`call_count` = every logged call, and `sales_calls` = calls that converted) and
no `month`/time dimension wired, so "last month" has nothing to bind to. The
right move is to **echo what you'd run and ask the analyst to disambiguate** —
not to guess one metric and execute.

Q2 is clear: one obvious metric (`total_revenue`) on `order_event`, one
compatible dimension (`country`). The right move is to echo the restatement and
execute.

Q3 is clear, but the metric lives on the decoy model: `partner_sourced_revenue`
is the only correct answer for "revenue from partners", and it lives on
`partner_directory` — a model that sounds like a reference/lookup table. The
tempting wrong path is to select `total_revenue` filtered by `channel='partner'`,
but `channel` is the order's own sales channel, not partner attribution. The
right move is to describe every model (including `partner_directory`), find
`partner_sourced_revenue`, echo it, and execute.

## Required artifacts from eval runner

- A running Nextdata OS data product exposing the three semantic MCP tools, loaded
  with the catalog in `fixtures/catalog.json`.
- MCP tool access configured for the agent session.

## Grading

Machine-graded against `checks.json` after the agent completes. The checks are not
revealed to the agent. In short: describe **every** model before building any
selection (coverage), echo the resolved selection in plain language, **clarify
(don't execute)** on the ambiguous Q1, **execute (don't over-clarify)** on clear
Q2 and Q3, use `partner_sourced_revenue` (not `total_revenue` with a channel
filter) for Q3, never author raw SQL, and note PII when a governed dimension is
selected.
