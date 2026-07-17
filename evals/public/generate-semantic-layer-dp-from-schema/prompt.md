# Scenario: Generate a Semantic-Layer Data Product from a Schema

The data-engineering team has two Snowflake tables — one entity-grain table (`customer_profile`, one row per customer) and one event-grain table (`order_event`, one row per order, FK-joined to `customer_profile` on `CUSTOMER_ID`). The tables are described in the schema fixture provided below.

Leadership wants an LLM-accessible analytics surface over these tables: a Nextdata OS data product that exposes governed metrics and dimensions via MCP, so business analysts can ask natural-language questions and get back aggregated, grain-safe answers without hand-writing SQL.

The skill being evaluated teaches how to build this kind of semantic-layer DP using the **`.semantic_tools()` pattern** (NEX-710): the author declares the semantic vocabulary as per-field `__nxd_semantic__` annotations on the model attributes, promises the models on the storage port, and adds a single `.semantic_tools(service=...)` flag that auto-generates the four governed MCP tools (`list_models`, `semantic_model`, `describe_model`, `run_semantic_query`) at pod boot. The compiler and tool factory ship in the `nxd.data_product` wheel (`nxd.experimental.semantic`) — imported, never re-implemented or vendored.

## Task for the agent

Build a Nextdata OS semantic-layer data product for the schema in `fixtures/schema.md`.

The data product must:

1. Author a `models.py` with two `semantic_model(...)` definitions (`customer_profile`, `order_event`) carrying per-field `__nxd_semantic__` annotations, with correct grains (a `{"kind": "grain"}` blob on `CUSTOMER_ID` / `ORDER_ID`).
2. Annotate at least the following metrics (via `{"kind": "metric", ...}` blobs):
   - Total revenue (`agg: "sum"` on `AMOUNT_USD` from `order_event`)
   - Order count (`agg: "count_distinct"` on `ORDER_ID` from `order_event`)
   - Churned customer count (counts customers where `IS_CHURNED` is true — `boolean: true`)
   - First-order count (counts orders where `IS_FIRST_ORDER` is true — `boolean: true`)
3. Annotate useful slicing dimensions from both tables, including country, segment, channel, order status, and order date (`{"kind": "dimension", ...}` blobs). Mark `EMAIL` and `FULL_NAME` with `"pii": true`.
4. Declare the join from `order_event` to `customer_profile` with a `{"kind": "join", "to_model": "customer_profile", "cardinality": "many_to_one"}` blob on the FK.
5. Wire `spec.py` so the four MCP tools are exposed via a single `.semantic_tools(service=...)` call — promising every annotated model on a plain `storage(...)` port — rather than hand-wiring `build_semantic_tools` + `rpc_function` + `rpc_server`, and rather than calling `data_product_rpc_output()` directly.
6. Author a `transform.py` that seeds the base tables (`CREATE OR REPLACE TABLE` + `write_pandas`) and a marker row, with no semantic-view DDL and no `@on_provision` hook.
7. Ensure `requirements.txt` (or `pyproject.toml`) includes the kit's dependencies, including `pyyaml` for the split-pod manifest fallback.

## Required artifacts from eval runner

- `fixtures/schema.md` — the source table definitions (provided).
- The `nxd.data_product` wheel (providing `nxd.experimental.semantic`, `semantic_model`, and the `.semantic_tools()` spec flag), available as an installed dependency per the skill's instructions.

## Note on the annotation stopgap

The public per-field author API (`AttributeSpec.semantic_annotation()`, NEX-704) is not yet merged; the skill teaches a clearly-marked stopgap that injects the `__nxd_semantic__` blob into `AttributeSpec._metadata` via a small `_annotate()` helper. Using that documented stopgap is correct for this scenario.
