# Scenario: Generate a Semantic-Layer Data Product from a Schema

The data-engineering team has two Snowflake tables — one entity-grain table (`customer_profile`, one row per customer) and one event-grain table (`order_event`, one row per order, FK-joined to `customer_profile` on `CUSTOMER_ID`). The tables are described in the schema fixture provided below.

Leadership wants an LLM-accessible analytics surface over these tables: a Nextdata OS data product that exposes governed metrics and dimensions via MCP, so business analysts can ask natural-language questions and get back aggregated, grain-safe answers without hand-writing SQL.

The skill being evaluated teaches how to build this kind of semantic-layer DP using the **`.semantic_tools()` pattern** (NEX-710): the author declares the semantic vocabulary with the public `nxd.spec` DSL, promises the physical models on the storage port, and adds a single `.semantic_tools(service=...)` flag that auto-generates the four governed MCP tools (`list_models`, `semantic_model`, `describe_model`, `run_semantic_query`) at pod boot. Physical models use `field(...)` roles; metrics use `metric_field(metric(...))` on a query-time `semantic_view(...)`. The compiler and tool factory ship in the `nxd.data_product` wheel — imported, never re-implemented or vendored.

## Task for the agent

Build a Nextdata OS semantic-layer data product for the schema in `fixtures/schema.md`.

The data product must:

1. Author a `models.py` with two physical `semantic_model(...)` definitions (`customer_profile`, `order_event`). Declare each key with `field(..., primary_key(), dimension(...))`, and give both models descriptions. Do not mutate private attribute metadata.
2. Add the following public-DSL metrics on one or more query-time `semantic_view(...)` objects using `metric_field(metric(...))`:
   - Total revenue (`Agg.SUM` over `order_event.field("AMOUNT_USD")`)
   - Order count (`Agg.COUNT_DISTINCT` over `order_event.field("ORDER_ID")`)
   - Churned customer count (`Agg.SUM` over `customer_profile.field("IS_CHURNED")`, with `boolean=True`)
   - First-order count (`Agg.SUM` over `order_event.field("IS_FIRST_ORDER")`, with `boolean=True`)
3. Add public `dimension(...)` roles for useful slicing fields from both tables, including country, segment, channel, order status, and order date. Mark `EMAIL` and `FULL_NAME` with `pii=True` and do not mark any other dimension as PII.
4. Declare the join from `order_event` to `customer_profile` with `field(..., join(to="customer_profile", to_column="CUSTOMER_ID"))` on the foreign key.
5. Wire `spec.py` so the four MCP tools are exposed via a single `.semantic_tools(service=...)` call — promising every annotated model on a plain `storage(...)` port — rather than hand-wiring `build_semantic_tools` + `rpc_function` + `rpc_server`, and rather than calling `data_product_rpc_output()` directly.
6. Author a `transform.py` that seeds the base tables (`CREATE OR REPLACE TABLE` + `write_pandas`) and a marker row, with no semantic-view DDL and no `@on_provision` hook.
7. Ensure `requirements.txt` (or `pyproject.toml`) includes the kit's dependencies, including `pyyaml` for the split-pod manifest fallback.

## Required artifacts from eval runner

- `fixtures/schema.md` — the source table definitions (provided).
- The `nxd.data_product` wheel (providing `nxd.experimental.semantic`, `semantic_model`, and the `.semantic_tools()` spec flag), available as an installed dependency per the skill's instructions.

## Public-DSL boundary

Use the public `nxd.spec` role builders taught by the skill. `primary_key()`,
`dimension(...)`, and `join(...)` belong on physical model fields; metrics belong
on a `semantic_view(...)` through `metric_field(metric(...))`. Descriptions for
concepts go inside `dimension(description=...)` and `metric(description=...)`,
while model descriptions use `.description(...)`. The old private
legacy private metadata and deprecated role vocabulary are not valid outputs
for this scenario.
