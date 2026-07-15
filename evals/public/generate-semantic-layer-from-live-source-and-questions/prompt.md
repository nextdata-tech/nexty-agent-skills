# Scenario: Generate a Semantic-Layer Data Product from a Live Source and Questions

Unlike the schema-transcription scenario, there is **no schema document** here. A sample of the operational database has already been landed into a local DuckDB file — the workspace ships a committed seed (`seed_tables.sql`) plus `build_fixture.py`, which materializes `source.duckdb` carrying two tables, `main.customers` and `main.orders` (the build step stands in for the dlt sample load that already ran in a real session). The only other input is a set of natural-language questions from business stakeholders.

The agent must **infer** the semantic model itself: profile the materialized tables into a `schema.json` handoff artifact (DESCRIBE + sampled rows + exact null% / cardinality), decide from that profile and the questions which columns are grains, dimensions, metrics (and with which aggregations), which join to declare, and which columns are PII — then author the data product and prove the questions are answerable by running the shipped acceptance test, which executes the four stakeholder queries against the declared concepts.

The skill being evaluated teaches how to build this kind of semantic-layer DP using the **`.semantic_tools()` pattern** (NEX-710), and — new for this scenario — how to derive the semantic vocabulary from a profiled source instead of a hand-provided schema: the author declares the inferred vocabulary as per-field `__nxd_semantic__` annotations on the model attributes, promises the models on the storage port, and adds a single `.semantic_tools(service=...)` flag that auto-generates the four governed MCP tools (`list_models`, `semantic_model`, `describe_model`, `run_semantic_query`) at pod boot. The compiler and tool factory ship in the `nxd.data_product` wheel (`nxd.experimental.semantic`) — imported, never re-implemented or vendored.

## Task for the agent

Build a Nextdata OS semantic-layer data product that lets an AI agent answer the stakeholder questions below over governed MCP tools.

1. Materialize the local sample: run `build_fixture.py` in your workspace (use `uv run --with duckdb python build_fixture.py` if the `duckdb` package is not installed). It writes `source.duckdb` containing `main.customers` and `main.orders`.
2. Profile both tables BEFORE authoring anything, and save the combined profile as **`schema.json`** in your workspace — actual columns, declared types, exact null rates and cardinalities, and sample values for both tables in one document. Ground every later decision in `schema.json`; do not invent, rename, or guess columns, and keep the file in place as the record of what you profiled.
3. From `schema.json` **and** the stakeholder questions, infer the semantic model: each table's grain, the dimensions worth slicing by, the metrics with correct aggregation functions, any cross-table relationship the questions require (validated against the data, not just name similarity), and any columns that must be flagged as PII. If a question's business definition is ambiguous against the profiled data, do not silently pick an interpretation — make the ambiguity and your resolution explicit.
4. Author the data product: `models.py` with per-field `__nxd_semantic__` annotations carrying the inferred vocabulary, a `transform.py` that seeds the base tables, and a `spec.py` that exposes the four governed MCP tools.
5. Verify your model answers the questions: run the shipped acceptance test — `uv run --with duckdb python check_semantic_model.py` (it loads your `models.py`, validates the roles against `source.duckdb`, and executes all four stakeholder questions from your declared concepts). It must print `ALL CHECKS PASSED`. If it fails, fix the model and re-run; do not finish with a failing check, and do not edit the acceptance test itself.
6. In your final answer, include: (a) the complete final `models.py` verbatim, (b) the acceptance-test result, (c) a question→concept mapping — for each of the four questions, which declared metrics/dimensions/joins answer it — and (d) any business-definition ambiguities you hit and the interpretation you chose.

## Stakeholder questions

1. "What's our total revenue by sales channel?"
2. "How many customers have churned, in each segment?"
3. "Which countries place the most orders?"
4. "What's the average order value?"

## Required artifacts from eval runner

- `fixtures/seed_tables.sql` + `fixtures/build_fixture.py` — the committed seed and the deterministic build step that materializes `source.duckdb` (provided; copied into the agent workspace).
- `fixtures/check_semantic_model.py` — the acceptance test (provided; copied into the agent workspace). It stubs the nxd spec API, so it runs without the nxd wheel; it needs only `duckdb`.
- The `nxd.data_product` wheel (providing `nxd.experimental.semantic`, `semantic_model`, and the `.semantic_tools()` spec flag), available as an installed dependency per the skill's instructions.
- The `duckdb` Python package must be obtainable in the workspace (e.g. via `uv run --with duckdb`), for the fixture build, the profiling step, and the acceptance test.

## Note on the annotation stopgap

The public per-field author API (`AttributeSpec.semantic_annotation()`, NEX-704) is not yet merged; the skill teaches a clearly-marked stopgap that injects the `__nxd_semantic__` blob into `AttributeSpec._metadata` via a small `_annotate()` helper. Using that documented stopgap is correct for this scenario.
