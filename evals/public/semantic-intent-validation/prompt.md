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

## What each question is testing (judge-only — not shown to the agent)

Everything below this heading and above `## Task for the agent` is stripped from
the agent's copy by `agent_task_from_prompt` in `evals/run.py`. It is written for
the judge. Naming the traps here rather than in the task section is deliberate:
if the task section told the agent to describe every model, or named
`partner_sourced_revenue`, the two coverage checks would grade prompt-following
instead of the skill, and a `no_skills` baseline would pass them.

**Q1 — "How many calls did we make last month?" — expect a clarify, not an
execution.** The catalog has two call-related metrics (`call_count` = every
logged call, `sales_calls` = calls that converted) at the same grain, and no
`month`/date/time dimension on any model, so "last month" has nothing to bind
to. The right move is to echo what would run and ask the analyst to
disambiguate — not to guess one metric and execute.

**Q2 — "What is the total revenue by country?" — expect an execution, no
clarify turn.** One obvious metric (`total_revenue` on `order_event`) and one
compatible dimension (`country`, reached through `order_event`'s documented join
to `customer_profile`). Adding a clarify turn here is over-clarifying.

**Q3 — "How much revenue did partners bring in?" — expect an execution, and it
is the discovery trap.** The only correct metric is `partner_sourced_revenue`,
and it lives on `partner_directory` — whose `list_models` row exposes nothing but
a name, a grain ("one row per partner") and a lookup-table-sounding description.
An agent that decides relevance before reading the model skips it, stops at
`order_event`, and selects `total_revenue` filtered by `channel = 'partner'`.
That returns a confident wrong number: `channel` is the order's own sales
channel, not partner attribution. The two paths are numerically distinguishable
against the seeded fixtures — the correct path returns 275, the trap returns 150
— so the transcript shows which one was taken.

## Task for the agent

A business analyst asks you three questions, in turn. Answer each one using the
semantic MCP tools available in your session, following the skill's Step 6f
intent gate.

> **Q1:** "How many calls did we make last month?"
>
> **Q2:** "What is the total revenue by country?"
>
> **Q3:** "How much revenue did partners bring in?"

Selections are concept names, not SQL — do not hand-author a SQL string.

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
