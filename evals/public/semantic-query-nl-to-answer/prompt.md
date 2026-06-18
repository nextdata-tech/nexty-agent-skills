# Scenario: Answer a Natural-Language Analytics Question via Semantic MCP Tools

A business analyst has access to a Nextdata OS data product that exposes four MCP tools:

- `list_metrics` — returns available metric names and descriptions
- `list_dimensions` — returns available dimension names and descriptions
- `describe_metric` — returns full metadata for one metric (including which dimensions are compatible)
- `run_semantic_query` — accepts a `{measures, dimensions, filters}` selection (concept names, not SQL) and returns the compiled SQL plus the result rows (capped at 200 rows, read-only, aggregated)

The data product covers an order-analytics domain: two tables (`customer_profile` at customer grain and `order_event` at order grain) joined on `CUSTOMER_ID`.

The analyst has submitted the following natural-language question:

> "What is the total revenue broken down by country?"

Your task is to answer this question using the available MCP tools.

## Task for the agent

Use the semantic MCP tools to answer the analyst's question. Do not write raw SQL. Produce a concise answer with the result data and a brief explanation of what the numbers represent.

## Required artifacts from eval runner

- A running Nextdata OS data product with the four semantic MCP tools registered (as would be produced by the `generate-semantic-layer-dp-from-schema` scenario or equivalent).
- MCP tool access configured for the agent session.

## Success checks

These checks are graded by the evaluator after the agent completes. Do not reveal them to the agent.

- **Discovery before query**: the agent calls `list_metrics` and/or `list_dimensions` (or `describe_metric`) before issuing `run_semantic_query`. Jumping straight to `run_semantic_query` with guessed concept names is a failure.
- **Selection uses concept names, not SQL**: the `run_semantic_query` call passes a `{measures, dimensions, filters}` dict with concept names (e.g. `"total_revenue"`, `"country"`) — it does not pass a raw SQL string or a `sql` key.
- **Correct measure selected**: the selection's `measures` list contains `"total_revenue"` (the SUM of `AMOUNT_USD`), not `order_count` or another metric.
- **Correct dimension selected**: the selection's `dimensions` list contains `"country"`.
- **Compiled SQL is aggregated**: the `compiled_sql` field in the tool response contains a `GROUP BY` clause and an aggregate function (`SUM`, `COUNT`, etc.) — it is not a flat row-level SELECT.
- **Compiled SQL is read-only**: the `compiled_sql` does not contain `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `DROP`, `MERGE`, or `TRUNCATE`.
- **Answer delivered**: the agent produces a final natural-language answer referencing the result rows (e.g. a table or bullet list of country → revenue), not just "the query ran successfully."
- **No raw SQL authored by agent**: the agent's messages do not contain a hand-written SQL string that was passed to a SQL execution tool outside of `run_semantic_query`.
