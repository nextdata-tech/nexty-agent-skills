# Scenario: Chasm-Trap Fan-Out Defended — Mixed-Grain Query Recovery

A business analyst has access to a Nextdata OS data product exposing four semantic MCP tools (`list_metrics`, `list_dimensions`, `describe_metric`, `run_semantic_query`) over an order-analytics domain.

The domain exposes metrics from two tables:

- `customer_profile` — customer data.
- `order_event` — order transaction data.

The analyst asks:

> "By country, how many customers have churned AND what is the total revenue?"

## Task for the agent

Answer the analyst's question using the available MCP tools.

## Required artifacts from eval runner

- A running Nextdata OS data product with the four semantic MCP tools registered.
- MCP tool access configured for the agent session.
