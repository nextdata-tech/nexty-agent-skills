# Compiler and routing

## Contents
- What the compiler does
- Three compile paths
- Chasm-trap defence (load-bearing correctness property)
- Filter rendering
- Snowflake dialect specifics
- Provisioning: native_semantic_view_ddl and plain_view_ddl
- Adding a new backend dialect

---

## What the compiler does

`compile_selection(selection, *, registry, dialect, fqn, use_view)` takes a
concept-level selection and produces a single read-only, aggregated SQL query.

Input `selection` shape:

```python
{
    "measures":   ["metric_name", ...],       # required
    "dimensions": ["dimension_name", ...],    # optional
    "filters": [
        {"dimension": "dim_name", "op": "=", "value": "foo"},
        ...
    ],                                        # optional
}
```

Output: a SQL string ready to execute (wrapped in `LIMIT cap+1` by the MCP tool).

The routing and validation logic is dialect-independent. Only the leaf SQL
expressions (aggregation, filter literals, native view DDL/query) are
dialect-specific.

---

## Three compile paths

### Path 1: single-model

All selected metrics and dimensions live on the same table. The compiler
emits a plain `SELECT ... FROM table WHERE ... GROUP BY ...`.

```sql
SELECT
  REGION AS region,
  COUNT(DISTINCT order_id) AS order_count
FROM DB.SCHEMA.orders
GROUP BY REGION
```

### Path 2: cross-model N:1 join (when `use_view=False`)

A dimension is on a different model than the metric, and a MANY_TO_ONE join
connects them. The compiler finds the first MANY_TO_ONE join from the metric's
model (MANY) to the dimension's model (ONE) and emits an inline JOIN:

```sql
SELECT
  r.CATEGORY AS category,
  COUNT(DISTINCT l.order_id) AS order_count
FROM DB.SCHEMA.orders l
JOIN DB.SCHEMA.products r ON l.product_id = r.product_id
GROUP BY r.CATEGORY
```

### Path 2 variant: compile against the pre-joined plain view (when `use_view=True`, the default)

Instead of an inline JOIN, the compiler queries the pre-created view
`<FIRST_MODEL>_SEMANTIC` (or the view name set on the dialect). This path is
simpler and avoids repeating join logic at query time:

```sql
SELECT
  CATEGORY AS category,
  COUNT(DISTINCT order_id) AS order_count
FROM DB.SCHEMA.ORDERS_SEMANTIC
GROUP BY CATEGORY
```

The plain view must have been created by `plain_view_ddl()` during provisioning.

### Path 3: native semantic view (Snowflake)

When the Snowflake `SEMANTIC VIEW` object exists in the session,
`run_semantic_query` prefers the native path via `semantic_view_query()`:

```sql
SELECT * FROM SEMANTIC_VIEW(DB.SCHEMA.ORDERS_SEMANTIC
  METRICS order_count
  DIMENSIONS category
  WHERE status = 'Active')
```

The MCP tool calls `dialect.supports_native_semantic_view(cursor)` to probe
existence. Falls back to path 2 on failure.

---

## Chasm-trap defence (load-bearing correctness property)

**This is the most important correctness invariant.** When a selection includes
metrics from two different model grains (e.g. `order_count` on `orders` and
`event_count` on `events`), the compiler raises:

```
CompileError: metrics span multiple grains (events, orders);
query one grain at a time to avoid fan-out double-counting.
Split into separate queries.
```

Fan-out double-counting occurs when two fact grains are joined: each row from
table A multiplies with each matching row from table B, so aggregates become
inflated without warning. The compiler detects this by checking that all selected
metrics share the same `model` field.

The `CompileError` message is intentionally phrased for the calling LLM so it
can correct its selection.

---

## Filter rendering

Filters reference dimension **concept names** (not physical columns). The
compiler resolves the concept name to the physical column internally.

Supported operators (exact symbols — not words):

```
=   !=   <>   >   >=   <   <=   LIKE   ILIKE   IN   NOT IN
```

For `IN` / `NOT IN`, `value` must be a list. For all others, a scalar.

Example filters:

```python
{"dimension": "region",   "op": "=",    "value": "EMEA"}
{"dimension": "category", "op": "IN",   "value": ["Electronics", "Software"]}
{"dimension": "event_date","op": ">=",  "value": "2024-01-01"}
```

An unknown dimension name raises `CompileError: unknown filter dimension 'X'`.
An unsupported `op` raises `CompileError: unsupported filter op '...'`.

---

## Snowflake dialect specifics

`SnowflakeDialect` generates SQL verified live against Snowflake.

### Aggregation expressions

| Agg | boolean=False | boolean=True |
|-----|---------------|--------------|
| COUNT(*) | `COUNT(*)` | — |
| COUNT_DISTINCT | `COUNT(DISTINCT col)` | — |
| SUM | `SUM(TRY_CAST(CAST(col AS VARCHAR) AS DOUBLE))` | `SUM(CASE WHEN CAST(col AS VARCHAR) IN ('true','TRUE','True','t','1','yes','YES') THEN 1 ELSE 0 END)` |
| AVG | `AVG(TRY_CAST(CAST(col AS VARCHAR) AS DOUBLE))` | — |
| MIN | `MIN(TRY_CAST(CAST(col AS VARCHAR) AS DOUBLE))` | — |
| MAX | `MAX(TRY_CAST(CAST(col AS VARCHAR) AS DOUBLE))` | — |

The double VARCHAR cast (`TRY_CAST(CAST(col AS VARCHAR) AS DOUBLE)`) tolerates
`NUMBER`, `FLOAT`, and `VARCHAR` physical column types, and staging text copies.
`TRY_CAST` returns NULL on parse failure (NULLs are ignored by aggregates).

### Fully-qualified name (fqn)

Pass `fqn="DB.SCHEMA."` (note trailing dot) to `compile_selection` or
`build_semantic_tools` so queries run independently of the Snowflake session's
active database/schema.

---

## Provisioning: native_semantic_view_ddl and plain_view_ddl

Two provisioning functions are available for the DP's provision step:

### `native_semantic_view_ddl(registry, dialect, fqn)`

Returns a `CREATE OR REPLACE SEMANTIC VIEW` DDL string (Snowflake-specific).
Emit this during the DP's provision transform to materialize the native object.
When it exists, `run_semantic_query` uses path 3.

### `plain_view_ddl(registry, dialect, fqn)`

Returns a `CREATE OR REPLACE VIEW ... AS SELECT ... FROM left JOIN right ON ...`
DDL. Dialect-independent fallback. Emit during provision as a stand-in when the
Snowflake SEMANTIC VIEW is not yet supported by the account tier.

Both functions derive the view name from the dialect (default:
`<FIRST_MODEL_UPPER>_SEMANTIC`). The same name is used by
`compile_selection(..., use_view=True)` so the paths are consistent.

---

## Adding a new backend dialect

Implement the `Dialect` Protocol:

```python
class Dialect(Protocol):
    def agg_expr(self, metric: Metric) -> str: ...
    def native_view_ddl(self, registry: CompiledRegistry, fqn: str) -> str | None: ...
    def native_view_query(self, registry, selection, fqn) -> str | None: ...
    def supports_native_semantic_view(self, cursor, fqn) -> bool: ...
```

Pass your dialect instance to `compile_selection(..., dialect=my_dialect)` and
`build_semantic_tools(registry, dialect=my_dialect)`.

Backends that do not support native semantic views should return `None` from
`native_view_ddl` and `native_view_query`, and `False` from
`supports_native_semantic_view`. The compiler falls back to the base-table /
plain-view path automatically.
