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
