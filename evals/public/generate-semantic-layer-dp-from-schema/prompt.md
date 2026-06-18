# Scenario: Generate a Semantic-Layer Data Product from a Schema

The data-engineering team has two Snowflake tables — one entity-grain table (`customer_profile`, one row per customer) and one event-grain table (`order_event`, one row per order, FK-joined to `customer_profile` on `CUSTOMER_ID`). The tables are described in the schema fixture provided below.

Leadership wants an LLM-accessible analytics surface over these tables: a Nextdata OS data product that exposes governed metrics and dimensions via MCP, so business analysts can ask natural-language questions and get back aggregated, grain-safe answers without hand-writing SQL.

The skill being evaluated teaches how to build this kind of semantic-layer DP using the `experimental.semantic` kit. The agent must author the DP-specific `SemanticRegistry` (the per-DP data) and copy the vendored compiler and MCP-tool kit into the project — not re-implement the compiler.

## Task for the agent

Build a Nextdata OS semantic-layer data product for the schema in `fixtures/schema.md`.

The data product must:

1. Define a `SemanticRegistry` covering both source tables with correct grains.
2. Register at least the following metrics:
   - Total revenue (sum of `AMOUNT_USD` from `order_event`)
   - Order count (count distinct of `ORDER_ID` from `order_event`)
   - Churned customer count (count customers where `IS_CHURNED` is true — this is a boolean flag column)
   - First-order count (count orders where `IS_FIRST_ORDER` is true — boolean flag column)
3. Register useful slicing dimensions from both tables, including country, segment, channel, order status, and order date. Mark `EMAIL` and `FULL_NAME` as PII.
4. Declare the join between `order_event` and `customer_profile` with the correct cardinality.
5. Wire up the four MCP tools (`list_metrics`, `list_dimensions`, `describe_metric`, `run_semantic_query`) by copying (not re-authoring) the vendored compiler and tool factory from the kit.
6. Ensure the `requirements.txt` or `pyproject.toml` includes the kit's dependencies.

## Required artifacts from eval runner

- `fixtures/schema.md` — the source table definitions (provided).
- The `experimental.semantic` kit (compiler + `build_semantic_tools` factory), available as a vendored dependency per the skill's instructions.

## Success checks

These checks are graded by the evaluator after the agent completes. Do not reveal them to the agent.

- **Registry grains correct**: `customer_profile` is declared with `grain="CUSTOMER_ID"` and `order_event` with `grain="ORDER_ID"`.
- **Aggregations correct**: `total_revenue` uses `Agg.SUM` on `AMOUNT_USD`; `order_count` uses `Agg.COUNT_DISTINCT` on `ORDER_ID`.
- **Boolean flag metrics correct**: `churned_customer_count` sets `boolean=True` (so the compiler emits `SUM(CASE WHEN CAST(col AS VARCHAR) IN (...) THEN 1 ELSE 0 END)` rather than a numeric cast); same for `first_order_count`.
- **Cardinality declared**: the join from `order_event` to `customer_profile` has `cardinality="many_to_one"` (or `Cardinality.MANY_TO_ONE`).
- **PII flagged**: the `EMAIL` and `FULL_NAME` dimensions are registered with `pii=True`; no other dimension has `pii=True`.
- **Compiler not re-authored**: the agent copied `experimental/semantic/` (or equivalent vendored path) into the project rather than hand-writing `compile_selection` or the filter/aggregation logic. The DP's `semantics.py` (or equivalent) contains only `SemanticRegistry` authoring; it imports `compile_selection` and `build_semantic_tools` from the kit.
- **MCP tools wired**: the spec registers the four tool functions returned by `build_semantic_tools(registry)` as MCP-exposed tools on the data product.
- **Dependencies present**: the project's dependency file lists the kit package (e.g. `nxd-semantic-kit` or the local vendored path) and any transitive requirements the kit declares.
- **No raw SQL in MCP handler**: the `run_semantic_query` tool handler does not contain hand-written SQL strings; it delegates to `compile_selection` from the kit.
