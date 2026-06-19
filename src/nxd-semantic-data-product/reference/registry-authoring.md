# Registry authoring guide

## Contents
- Core concepts
- SemanticRegistry fluent API
- Agg enum (closed)
- Cardinality enum
- Auto-derivation of cross-model dimension reach
- Worked generic example: people + events
- Validation rules enforced by build()
- from_dict() declarative constructor
- Common mistakes

---

## Core concepts

A **registry** is a frozen description of your semantic model: which tables
exist, which columns are dimensions or metrics, and how tables relate. The
registry is authored once per data product and passed to `build_semantic_tools()`
to produce the three MCP tools (`list_models`, `describe_model`, `run_semantic_query`).

The registry has four element types:

| Type | What it represents |
|------|--------------------|
| `Model` | A physical table with a grain (entity key column) |
| `Dimension` | A column an agent can group or filter by |
| `Metric` | A named aggregated measure |
| `Join` | A documented relationship between two models |

---

## SemanticRegistry fluent API

```python
from nxd.experimental.semantic import Agg, Cardinality, SemanticRegistry

registry = (
    SemanticRegistry()
    .model(name, *, grain, description="")
    .dimension(name, *, model, column, type="string", description="", pii=False)
    .metric(name, *, model, agg, column="*", description="", boolean=False,
            extra_dimensions=())
    .join(*, left, right, on, cardinality=Cardinality.MANY_TO_ONE)
    .build()
)
```

### `.model(name, *, grain, description="")`

Declares a physical table.

- `name` — unique string identifier for the model, matching the table name.
- `grain` — the column (or comma-separated columns) that uniquely identifies one
  row: the entity key. Required.
- `description` — optional human description surfaced in tool responses.

### `.dimension(name, *, model, column, type, description, pii)`

Declares a slicing / filtering axis.

- `name` — unique concept name used in `run_semantic_query` and surfaced in a
  model's `describe_model` `dimensions` list.
- `model` — must match a declared model name.
- `column` — physical column name in the table (case-insensitive at query time).
- `type` — logical type hint: `"string"`, `"date"`, `"number"`, etc. Informational
  only; does not affect SQL generation.
- `description` — plain-language description for the agent.
- `pii=True` — marks the dimension as a governance target. PII dimensions appear
  in `describe_model` with a flag; the query layer may mask or reject them
  depending on the caller's access level.

### `.metric(name, *, model, agg, column, description, boolean, extra_dimensions)`

Declares a named aggregated measure.

- `name` — unique concept name (e.g. `"order_count"`, `"revenue"`).
- `model` — must match a declared model name.
- `agg` — one of `Agg.COUNT`, `Agg.COUNT_DISTINCT`, `Agg.SUM`, `Agg.AVG`,
  `Agg.MIN`, `Agg.MAX`.
- `column` — physical column to aggregate. Use `"*"` for `COUNT(*)`.
- `boolean=True` — the column is a boolean/flag. SQL becomes
  `SUM(CASE WHEN CAST(col AS VARCHAR) IN ('true','TRUE','1','yes',...) THEN 1 ELSE 0 END)`,
  robust to BOOLEAN and VARCHAR physical types.
- `extra_dimensions` — explicit override tuple of dimension names this metric can
  be sliced by beyond its own model's dimensions. **Leave empty** (default) to let
  `build()` auto-derive cross-model reach from N:1 joins. Use only as an override
  for a specific metric when the auto-derived set is incorrect.

### `.join(*, left, right, on, cardinality)`

Declares a documented join between two models.

- `left` — model name on the MANY side (the fact table).
- `right` — model name on the ONE side (the dimension table).
- `on` — tuple of `(left_col, right_col)` pairs.
- `cardinality` — defaults to `Cardinality.MANY_TO_ONE`. Only MANY_TO_ONE joins
  trigger cross-model dimension auto-derivation and are used in the cross-model
  compile path.

### `.build() -> CompiledRegistry`

Validates and freezes the registry. Raises `ValueError` on:

- Duplicate model / metric / dimension names.
- Empty grain on any model.
- Metric or dimension referencing an undeclared model.
- Join endpoint referencing an undeclared model.

---

## Agg enum (closed)

```python
class Agg(str, Enum):
    COUNT          = "count"
    COUNT_DISTINCT = "count_distinct"
    SUM            = "sum"
    AVG            = "avg"
    MIN            = "min"
    MAX            = "max"
```

No custom aggregation functions. These six values are the closed vocabulary,
intentionally aligned with ADR-026.

---

## Cardinality enum

```python
class Cardinality(str, Enum):
    ONE_TO_ONE   = "one_to_one"
    ONE_TO_MANY  = "one_to_many"
    MANY_TO_ONE  = "many_to_one"   # the safe cross-model case
    MANY_TO_MANY = "many_to_many"
```

Only `MANY_TO_ONE` joins make cross-model dimension slicing safe (the MANY
side's grain is preserved through the join). Only MANY_TO_ONE joins appear in
the Snowflake `CREATE SEMANTIC VIEW` RELATIONSHIPS clause.

---

## Auto-derivation of cross-model dimension reach

When `build()` runs, for every metric whose `extra_dimensions` is empty
(the default), it inspects all MANY_TO_ONE joins where the metric's model is on
the left (MANY) side. The right (ONE) side's **non-PII** dimensions are added to
that metric's reachable dimension set in the compiled registry.

This means: if `orders` is joined to `products` via a MANY_TO_ONE join, and
`order_count` lives on `orders`, then `order_count` can be sliced by
`products`-model dimensions (`category`, `brand`, etc.) automatically — without
listing them in `extra_dimensions`.

PII dimensions on the ONE side are excluded from auto-derivation; they stay
accessible from their own model's queries but do not silently propagate to
joined metrics.

---

## Worked generic example: people + events

This example uses a two-model registry (people + activity events) with no
domain-specific names.

```python
from nxd.experimental.semantic import Agg, Cardinality, SemanticRegistry

REGISTRY = (
    SemanticRegistry()
    # Models
    .model(
        "people",
        grain="person_id",
        description="One row per person in the system.",
    )
    .model(
        "activity_events",
        grain="event_id",
        description="One row per activity event; FK to people.",
    )
    # Dimensions on people
    .dimension(
        "country",
        model="people",
        column="COUNTRY_CODE",
        type="string",
        description="ISO-2 country code of the person.",
    )
    .dimension(
        "signup_cohort",
        model="people",
        column="SIGNUP_MONTH",
        type="date",
        description="Month (YYYY-MM) in which the person signed up.",
    )
    .dimension(
        "email",
        model="people",
        column="EMAIL",
        type="string",
        description="Person's email address.",
        pii=True,   # governed — masked for non-privileged callers
    )
    # Dimensions on activity_events
    .dimension(
        "event_type",
        model="activity_events",
        column="EVENT_TYPE",
        type="string",
        description="Category of the activity event.",
    )
    .dimension(
        "event_date",
        model="activity_events",
        column="EVENT_DATE",
        type="date",
        description="Calendar date the event occurred.",
    )
    # Metrics on activity_events (fact grain)
    .metric(
        "event_count",
        model="activity_events",
        agg=Agg.COUNT,
        column="*",
        description="Total number of activity events.",
    )
    .metric(
        "unique_actors",
        model="activity_events",
        agg=Agg.COUNT_DISTINCT,
        column="person_id",
        description="Distinct people who had at least one event.",
    )
    # Metric on people (dimension grain)
    .metric(
        "total_people",
        model="people",
        agg=Agg.COUNT,
        column="*",
        description="Total number of people in the system.",
    )
    # N:1 join: many events -> one person
    .join(
        left="activity_events",
        right="people",
        on=(("person_id", "person_id"),),
        cardinality=Cardinality.MANY_TO_ONE,
    )
    .build()
)
```

After `build()`:

- `event_count` and `unique_actors` (on `activity_events`) can be sliced by
  `country` and `signup_cohort` (on `people`) — auto-derived from the N:1 join.
  `email` is excluded from auto-derivation because `pii=True`.
- `total_people` (on `people`) can be sliced by `country` and `signup_cohort`
  directly (same model). It cannot be sliced by `event_type` or `event_date`
  because those are on the MANY side, and auto-derivation only runs from MANY
  to ONE.

---

## Validation rules enforced by build()

| Rule | Error |
|------|-------|
| Duplicate model name | `Duplicate model name 'X'` |
| Duplicate metric name | `Duplicate metric name 'X'` |
| Duplicate dimension name | `Duplicate dimension name 'X'` |
| Empty grain on a model | `Model 'X' must declare a non-empty grain` |
| Metric references undeclared model | `Metric 'X' references undeclared model 'Y'` |
| Dimension references undeclared model | `Dimension 'X' references undeclared model 'Y'` |
| Join endpoint references undeclared model | `Join 'A' -> 'B': left/right endpoint 'X' is not a declared model` |

---

## from_dict() declarative constructor

For YAML-driven or JSON-driven registries, use `SemanticRegistry.from_dict(data)`:

```python
data = {
    "models": [{"name": "orders", "grain": "order_id"}],
    "dimensions": [{"name": "region", "model": "orders", "column": "REGION"}],
    "metrics": [{"name": "order_count", "model": "orders", "agg": "count_distinct",
                 "column": "order_id"}],
    "joins": [],
}
registry = SemanticRegistry.from_dict(data).build()
```

The `agg` field accepts both the string value (`"count_distinct"`) and the enum
member.

---

## Common mistakes

**Mistake**: putting two metrics from different models in one `run_semantic_query`
call.
**Result**: `CompileError: metrics span multiple grains (...); query one grain at
a time`.
**Fix**: split into two separate queries.

**Mistake**: referencing a dimension that isn't on the metric's model and isn't
reachable via a documented N:1 join.
**Result**: `CompileError: dimension 'X' is not compatible with metric 'Y'`.
**Fix**: add the join to the registry, or check that the dimension is on the
correct model.

**Mistake**: setting `extra_dimensions` explicitly when only auto-derivation is
needed.
**Result**: no error, but the explicit tuple overrides the auto-derived set
entirely, possibly hiding reachable dimensions.
**Fix**: leave `extra_dimensions=()` (the default) and let `build()` derive the
set.

**Mistake**: using the `column` name in a filter `op` instead of the dimension
concept name.
**Result**: `CompileError: unknown filter dimension 'PHYSICAL_COL_NAME'`.
**Fix**: use the dimension's `name` field, not its `column`.
