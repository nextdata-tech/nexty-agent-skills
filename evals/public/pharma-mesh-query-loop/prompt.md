# Scenario: Query a Pharma Semantic Mesh (governed MCP)

A clinical-data analyst has a Nextdata OS data product exposing a **pharma semantic
mesh** over three governed MCP tools — `list_models`, `describe_model`,
`run_semantic_query`. The mesh has a `subjects` spine and four MANY-per-subject
fact models (`visits`, `assays`, `dispenses`, `adverse_events`), each joinable to
the subject. It contains **confusable concepts** (more than one metric whose name
loosely matches a question) and **PII dimensions** that don't fit every grain.

## Task for the agent

Answer the analyst's questions below **using the governed semantic protocol** of
the `nxd-data-product-query` skill: discover the catalog via `list_models` /
`describe_model`, build a concept-name selection, run the intent gate, and call
`run_semantic_query` (never author raw SQL). For each question, restate what
you'll run in plain language before executing, and clarify rather than guess when
the question is ambiguous.

The analyst asks, in turn:

1. How many subjects are in the registry?
2. Total assay titer by subject country.
3. Per subject country, give me both total titer and total units dispensed.
4. By country: total visit duration, total titer, and total units dispensed.
5. What's the titer level by assay type?
6. How much was dispensed per channel?
7. How many serious adverse events were there, by adverse-event term?
8. Count the adverse events by term.
9. Show units dispensed broken down by prescriber.
10. How many visits did we have, by visit type?
11. What is the total units dispensed? (grand total, no breakdown)

## Required artifacts from eval runner

- A running data product exposing the three semantic MCP tools, loaded with the
  pharma catalog. MCP tool access configured for the agent session.

## Grading

Machine-graded against `checks.json` after the agent completes (checks not
revealed to the agent). In short: discover before querying, use the skill's
MCP toolchain, pick the right metric for each confusable question (or clarify),
get the fan-out-safe answer for multi-fact questions, surface PII governance, and
never author raw SQL.
