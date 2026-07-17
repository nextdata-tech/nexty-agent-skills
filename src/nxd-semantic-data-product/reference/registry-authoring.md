# Semantic annotation authoring guide

## Contents
- Core concepts
- The `__nxd_semantic__` role grammar
- Agg vocabulary (closed)
- Cardinality vocabulary
- Multi-role columns
- Auto-derivation of cross-model dimension reach
- Worked generic example: people + events
- Validation rules
- Common mistakes

---

## Core concepts

A **registry** is a frozen description of your semantic model: which tables exist,
which columns are dimensions or metrics, and how tables relate. Under the
`.semantic_tools()` pattern you do **not** build the registry with a fluent
`SemanticRegistry()` builder — you declare it as **per-field `__nxd_semantic__`
annotations** on each promised model's attributes. The kernel compiles the
annotations into the same frozen `CompiledRegistry` at boot and delivers it to the
pod (`<root>/.nxd/semantic/<model>.json`).

The registry has four element types, each expressed as a role blob on a column:

| Type | What it represents | Blob `kind` |
|------|--------------------|-------------|
| Model | A physical table with a grain (entity key column) | (the `semantic_model(...)` itself; grain via `{"kind": "grain"}`) |
| Dimension | A column an agent can group or filter by | `dimension` |
| Metric | A named aggregated measure | `metric` |
| Join | A documented relationship between two models | `join` |

> The fluent `SemanticRegistry().model().dimension().metric().join().build()`
> builder still exists in `nxd.experimental.semantic` — but it is now the
> **runtime reconstruction engine** (`build_semantic_tools_from_payload` feeds
> payloads through `SemanticRegistry.from_dict().build()`), not the author surface.
> Author with `__nxd_semantic__` blobs.

---

## The `__nxd_semantic__` role grammar

Each model attribute carries at most one `__nxd_semantic__` blob, injected via the
`_annotate()` stopgap (see SKILL.md Step 2). The blob is a JSON object — either a
single bare role (`{"kind": ...}`) or a multi-role wrapper (`{"roles": [...]}`).

### grain

```json
{"kind": "grain"}
```

Marks the column as (part of) the model's grain — the entity key that uniquely
identifies one row. Every model needs at least one grain column. Multiple grain
columns form a composite grain.

### dimension

```json
{"kind": "dimension",
 "name": "<concept_name>",
 "description": "<plain-language description>",
 "type": "string|date|number",
 "pii": false,
 "label_column": "<optional column holding a display label>"}
```

- `name` — unique concept name used in `run_semantic_query` and surfaced in
  `describe_model`. Required.
- `description` — plain-language description for the agent.
- `type` — logical type hint; informational, does not affect SQL.
- `pii` — `true` marks the dimension a governance target (flagged in
  `describe_model`; may be masked/rejected per caller access). Default `false`.
- The physical column is the attribute the blob is attached to.

### metric

```json
{"kind": "metric",
 "name": "<concept_name>",
 "agg": "count|count_distinct|sum|avg|min|max",
 "description": "<plain-language description>",
 "boolean": false,
 "extra_dimensions": ["<dim>", ...]}
```

- `name` — unique concept name (e.g. `order_count`, `revenue`). Required.
- `agg` — one of the six closed aggregations (see below). Required.
- `boolean` — `true` when the column is a flag; SQL becomes a CASE-sum
  (`SUM(CASE WHEN ... THEN 1 ELSE 0 END)`), robust to BOOLEAN and VARCHAR physical
  types, instead of a numeric cast-sum. Default `false`. **Requires
  `agg: "sum"`** — the dialect defines the boolean CASE expression only for
  `sum` (see `compiler-and-routing.md`); `boolean: true` with any other agg is
  invalid.
- `extra_dimensions` — explicit override of the dimensions this metric can be
  sliced by. **Leave unset** to let the compiler auto-derive cross-model reach from
  N:1 joins. Use only when the auto-derived set is wrong.
- The physical column is the attribute the blob is attached to. For a bare
  `COUNT(*)`-style total, anchor the metric on the grain column with
  `agg: "count"` (see the multi-role example).

### join

```json
{"kind": "join",
 "to_model": "<other model name>",
 "to_column": "<column on the other model>",
 "cardinality": "many_to_one"}
```

- Declared on the **MANY-side** model's join-key column.
- `to_model` — the ONE-side model. Required.
- `to_column` — the join key on the ONE side (defaults to the same column name).
- `cardinality` — defaults to `many_to_one` (the only cardinality that makes
  cross-model dimension slicing safe).

---

## Agg vocabulary (closed)

```
count   count_distinct   sum   avg   min   max
```

No custom aggregation functions. These six values are the closed vocabulary,
aligned with the planned first-class DSL. (The Python `Agg` enum mirrors them:
`Agg.COUNT`, `Agg.COUNT_DISTINCT`, `Agg.SUM`, `Agg.AVG`, `Agg.MIN`, `Agg.MAX`.)

---

## Cardinality vocabulary

```
one_to_one   one_to_many   many_to_one   many_to_many
```

Only `many_to_one` joins make cross-model dimension slicing safe (the MANY side's
grain is preserved through the join) and trigger cross-model dimension
auto-derivation. (`Cardinality.MANY_TO_ONE` is the enum form.)

---

## Multi-role columns

One column often plays two roles — a grain column that is also a `count` metric,
or a join key that is also a `count_distinct` metric. Use the `{"roles": [...]}`
wrapper. Because the bare `{"kind": ...}` shorthand has no inline multi-role form,
the idiom is to write the grain blob first, then **patch a full roles list
post-hoc** (the roles list REPLACES the bare blob):

```python
# CUSTOMER_ID is a join key AND a count_distinct metric.
"CUSTOMER_ID": _annotate(
    AttributeSpec(name="CUSTOMER_ID", data_type=int64()),
    {"roles": [
        {"kind": "join", "to_model": "customer_profile",
         "to_column": "CUSTOMER_ID", "cardinality": "many_to_one"},
        {"kind": "metric", "name": "unique_customers_ordered",
         "agg": "count_distinct",
         "description": "Distinct customers who placed an order."},
    ]},
),

# ORDER_ID is the grain AND a count metric — patched post-hoc.
_annotate(
    order_event._attributes["ORDER_ID"],
    {"roles": [
        {"kind": "grain"},
        {"kind": "metric", "name": "order_count", "agg": "count",
         "description": "Total number of orders."},
    ]},
)
```

---

## Auto-derivation of cross-model dimension reach

When the kernel compiles the registry, for every metric whose `extra_dimensions`
is unset (the default), it inspects all `many_to_one` joins where the metric's
model is on the MANY side. The ONE side's **non-PII** dimensions are added to that
metric's reachable dimension set.

So if `orders` joins to `products` via a `many_to_one` join and `order_count` lives
on `orders`, then `order_count` can be sliced by `products`-model dimensions
(`category`, `brand`, …) automatically — without listing them in
`extra_dimensions`. PII dimensions on the ONE side are excluded from
auto-derivation; they stay accessible from their own model's queries but do not
silently propagate to joined metrics.

---

## Worked generic example: people + events

Two models (people + activity events), no domain-specific names.

```python
import json

from nxd.spec import semantic_model
from nxd.spec._model import AttributeSpec
from nxd.spec.data_types import int64, string

_SEMANTIC_KEY = "__nxd_semantic__"


def _annotate(attr: AttributeSpec, role: dict) -> AttributeSpec:
    attr._metadata[_SEMANTIC_KEY] = json.dumps(role, separators=(",", ":"))
    return attr


people = (
    semantic_model("people")
    .description("One row per person in the system.")
    .schema({
        "PERSON_ID": _annotate(
            AttributeSpec(name="PERSON_ID", data_type=int64()),
            {"kind": "grain"},
        ),
        "COUNTRY_CODE": _annotate(
            AttributeSpec(name="COUNTRY_CODE", data_type=string(),
                          _description="ISO-2 country code."),
            {"kind": "dimension", "name": "country",
             "description": "ISO-2 country code of the person.", "type": "string"},
        ),
        "EMAIL": _annotate(
            AttributeSpec(name="EMAIL", data_type=string(),
                          _description="Person's email."),
            {"kind": "dimension", "name": "email",
             "description": "Person's email address.", "type": "string",
             "pii": True},
        ),
    })
)
# total_people = COUNT on the people grain.
_annotate(
    people._attributes["PERSON_ID"],
    {"roles": [
        {"kind": "grain"},
        {"kind": "metric", "name": "total_people", "agg": "count",
         "description": "Total number of people."},
    ]},
)

activity_events = (
    semantic_model("activity_events")
    .description("One row per activity event; FK to people.")
    .schema({
        "EVENT_ID": _annotate(
            AttributeSpec(name="EVENT_ID", data_type=int64()),
            {"kind": "grain"},
        ),
        "EVENT_TYPE": _annotate(
            AttributeSpec(name="EVENT_TYPE", data_type=string(),
                          _description="Event category."),
            {"kind": "dimension", "name": "event_type",
             "description": "Category of the activity event.", "type": "string"},
        ),
        # join key + count_distinct metric.
        "PERSON_ID": _annotate(
            AttributeSpec(name="PERSON_ID", data_type=int64()),
            {"roles": [
                {"kind": "join", "to_model": "people",
                 "to_column": "PERSON_ID", "cardinality": "many_to_one"},
                {"kind": "metric", "name": "unique_actors", "agg": "count_distinct",
                 "description": "Distinct people who had at least one event."},
            ]},
        ),
    })
)
# event_count = COUNT on the events grain.
_annotate(
    activity_events._attributes["EVENT_ID"],
    {"roles": [
        {"kind": "grain"},
        {"kind": "metric", "name": "event_count", "agg": "count",
         "description": "Total number of activity events."},
    ]},
)
```

After compilation:

- `event_count` and `unique_actors` (on `activity_events`) can be sliced by
  `country` (on `people`) — auto-derived from the N:1 join. `email` is excluded
  (PII).
- `total_people` (on `people`) can be sliced by `country` directly (same model). It
  cannot be sliced by `event_type` because that is on the MANY side, and
  auto-derivation only runs MANY → ONE.

---

## Validation rules

The kernel's compile rejects (errors surface at `nxd launch` build / pod boot):

| Rule | Error |
|------|-------|
| Duplicate model name | `Duplicate model name 'X'` |
| Duplicate metric name | `Duplicate metric name 'X'` |
| Duplicate dimension name | `Duplicate dimension name 'X'` |
| Empty grain on a model | `Model 'X' must declare a non-empty grain` |
| Metric/dimension on an un-promised model | the model's payload is never written; the tool never sees it |
| Join `to_model` references an undeclared model | `Join 'A' -> 'B': endpoint 'X' is not a declared model` |
| `agg` outside the closed vocabulary | rejected at blob parse |

---

## Common mistakes

**Mistake**: annotating a model but not `.promise(...)`-ing it in `spec.py`.
**Result**: the model's attributes never reach the manifest, so no
`.nxd/semantic/<model>.json` payload is written; the tools never see it.
**Fix**: `.promise(<model>)` every annotated model on the storage port.

**Mistake**: writing a bare `{"kind": "grain"}` AND a separate
`{"kind": "metric"}` blob on the same column (two `_annotate()` calls).
**Result**: the second blob overwrites the first — only the metric role survives,
the grain is lost.
**Fix**: use a single `{"roles": [...]}` blob, or patch the full roles list
post-hoc (see Multi-role columns).

**Mistake**: putting two metrics from different models in one
`run_semantic_query` call.
**Result**: `CompileError: metrics span multiple grains (...); query one grain at
a time`.
**Fix**: split into two queries.

**Mistake**: referencing a dimension not on the metric's model and not reachable
via a documented N:1 join.
**Result**: `CompileError: dimension 'X' is not compatible with metric 'Y'`.
**Fix**: add the join blob, or check the dimension is on the right model.

**Mistake**: setting `extra_dimensions` when only auto-derivation is needed.
**Result**: no error, but the explicit list overrides the auto-derived set,
possibly hiding reachable dimensions.
**Fix**: omit `extra_dimensions` and let the compiler derive the set.
