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

## Success checks

These checks are graded by the evaluator after the agent completes. Do not reveal them to the agent.

- **Mixed-grain call attempted**: the agent attempts a `run_semantic_query` call that includes metrics from both grains (e.g. `churned_customer_count` and `total_revenue` together) in one selection, OR — if the agent discovers the incompatibility from `describe_metric` before calling `run_semantic_query` — it explicitly acknowledges that a single combined query is not possible and explains why. Either path is acceptable; the key is the agent must confront the incompatibility, not silently drop one metric.
- **CompileError returned (if mixed-grain call is made)**: when the agent issues the mixed-grain `run_semantic_query`, the tool returns an error message containing "metrics span multiple grains" (or equivalent wording from the kit). The agent must not treat this as a transient failure to retry identically.
- **Recovery by splitting**: after receiving the error (or discovering the incompatibility), the agent issues at least two separate `run_semantic_query` calls — one per grain — rather than combining them or abandoning the question.
- **Per-grain queries are correct**: query 1 selects `churned_customer_count` with `country` dimension (customer grain, no fan-out); query 2 selects `total_revenue` with `country` dimension (order grain, joined N:1 to get country).
- **No raw SQL authored**: the agent does not attempt to work around the error by writing a hand-crafted SQL join that combines both metrics.
- **Final answer is coherent**: the agent delivers a final response presenting both result sets (churned customers by country, total revenue by country) and explains to the analyst that the two metrics operate at different grains and therefore require separate queries.
- **Explanation of grain safety**: the agent's explanation mentions that combining the metrics in one query would produce incorrect (double-counted) numbers, demonstrating understanding of why the split is necessary — not just that "the tool returned an error."
