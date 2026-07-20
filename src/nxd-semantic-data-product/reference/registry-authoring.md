# Semantic authoring guide

## Contents
- Core concepts
- Public role grammar
- Metrics on semantic views
- Cross-model dimensions
- Worked example
- Validation and common mistakes

---

## Core concepts

A semantic registry describes physical models, their entity keys and dimensions,
their N:1 relationships, and the metrics available over each model. Author it
only with the public `nxd.spec` DSL:

| Element | Where it belongs | Public form |
|---|---|---|
| Entity key | Physical `semantic_model` field | `field(type, primary_key())` |
| Dimension | Physical `semantic_model` field | `field(type, dimension(...))` |
| Join | Physical `semantic_model` field | `field(type, join(...))` |
| Metric | Query-time `semantic_view` field | `metric_field(type, metric(...))` |

Every physical model has one or more entity-key fields. Multiple
`primary_key()` fields define a composite key. A semantic view belongs to one
base model and is registered with `.model(view)` on the output; it is never
promised or written by the transform.

---

## Public role grammar

```python
from nxd.spec import Agg, dimension, field, join, metric, metric_field
from nxd.spec import primary_key, semantic_model, semantic_view
from nxd.spec.data_types import float64, int64, string
```

### Entity key

```python
"ORDER_ID": field(int64(), primary_key())
```

The key must identify one row of the physical model. Use more than one field when
the source has a validated composite key.

### Dimension

```python
"COUNTRY": field(
    string(),
    dimension(name="country", pii=False),
)
```

`name` is the stable concept used in a semantic query, and `pii=True` marks
governed personal data.

### Join

```python
"CUSTOMER_ID": field(
    int64(),
    join(to="customer_profile", to_column="CUSTOMER_ID"),
)
```

Declare the join on the many-side foreign key. `to` is the one-side model and
`to_column` is its entity key. Only a validated many-to-one relationship is safe
for slicing a fact metric by dimensions from the related model.

---

## Metrics on semantic views

Do not add a metric role to a physical base field. A metric is a query-time view
field that names an aggregation over a base-model column:

```python
order_metrics = semantic_view("order_metrics", orders).schema(
    {
        "order_count": metric_field(
            int64(),
            metric(Agg.COUNT, of=orders.field("ORDER_ID"), name="order_count"),
        ),
        "total_revenue": metric_field(
            float64(),
            metric(Agg.SUM, of=orders.field("AMOUNT_USD"), name="total_revenue"),
        ),
        "unique_customers": metric_field(
            int64(),
            metric(
                Agg.COUNT_DISTINCT,
                of=orders.field("CUSTOMER_ID"),
                name="unique_customers",
            ),
        ),
    }
)
```

The aggregation vocabulary is closed: `Agg.COUNT`, `Agg.COUNT_DISTINCT`,
`Agg.SUM`, `Agg.AVG`, `Agg.MIN`, and `Agg.MAX`. Put boolean counts on a `SUM`
metric over the flag field only when the intended result is a count of truthy
rows.

---

## Cross-model dimensions

The compiler derives compatible dimensions from a validated N:1 join. If
`orders.CUSTOMER_ID` joins to `customer_profile.CUSTOMER_ID`, metrics on the
`orders` view can be sliced by non-PII customer dimensions such as `country`.
Do not model a many-to-many relationship as a direct semantic join; it can change
the fact row count and invalidate metric results.

---

## Worked example: people and events

```python
from nxd.spec import Agg, dimension, field, join, metric, metric_field
from nxd.spec import primary_key, semantic_model, semantic_view
from nxd.spec.data_types import int64, string

people = semantic_model("people").schema(
    {
        "PERSON_ID": field(int64(), primary_key()),
        "COUNTRY_CODE": field(
            string(),
            dimension(name="country"),
        ),
        "EMAIL": field(
            string(),
            dimension(name="email", pii=True),
        ),
    }
)

activity_events = semantic_model("activity_events").schema(
    {
        "EVENT_ID": field(int64(), primary_key()),
        "EVENT_TYPE": field(
            string(),
            dimension(name="event_type"),
        ),
        "PERSON_ID": field(
            int64(),
            join(to="people", to_column="PERSON_ID"),
        ),
    }
)

event_metrics = semantic_view("event_metrics", activity_events).schema(
    {
        "event_count": metric_field(
            int64(),
            metric(Agg.COUNT, of=activity_events.field("EVENT_ID"), name="event_count"),
        ),
        "unique_actors": metric_field(
            int64(),
            metric(
                Agg.COUNT_DISTINCT,
                of=activity_events.field("PERSON_ID"),
                name="unique_actors",
            ),
        ),
    }
)
```

`event_count` and `unique_actors` can be sliced by `country`; the PII `email`
dimension is not propagated to the related metrics.

---

## Validation and common mistakes

- Use a unique, non-null source key for every physical model. Do not synthesize
  a key just to make the model compile.
- Keep physical names and field names identical to the actual table and source
  columns. The transform must seed the same physical tables.
- Promise every physical base with `.promise(base)`. Register every metric view
  with `.model(view)`.
- Do not put metrics from different base models into one semantic query. Query
  each model separately.
- Do not use a relationship until foreign-key containment and the target key's
  uniqueness have been validated.
