# Semantic models

## Contents
- Model details (builder methods)
- Semantic roles
- Linking models (Predicates)
- Metrics and semantic views
- Primitive types
- Complex types
- Field verifiers

Let's start by looking at an example of a semantic model that will be used in the spec file:

```python
from nxd.spec import Agg, Predicate, SamplingMethod, all_of, dimension, field, join, metric, metric_field
from nxd.spec import primary_key, semantic_model, semantic_view
from nxd.spec.data_types import float64, int64, string
from nxd.spec.validations import greater_than, match_regex

trending_sales = (
    semantic_model("trending_sales")
    .sampling(method=SamplingMethod.Random)
    .description("Measures and compares the rate of sales growth per channel...")
    .schema(
        {
            "sale_id": field(
                int64(),
                primary_key(),
                # Roles compose, and a key needs the pairing: primary_key()
                # alone never reaches describe_models, so no query can group by
                # it and "which sale..." has no answerable form.
                dimension(name="sale_id", description="Sale key. Group by this to name a sale."),
            ),
            "product_id": field(
                string(),
                join(to="products", to_column="product_id"),
            ),
            "sales_channel": field(
                string(),
                dimension(
                    name="sales_channel",
                    description="Sales channel from which transaction data was aggregated.",
                ),
            ),
            "amount_usd": float64(),
        }
    )
    .link(
        "product_id",
        Predicate.SameAs,
        "/data-product/sales#/models/transactions/attributes/product_code",
    )
    .when(all_of(channel_sales_velocity, ...))
    .verify_field("sale_id", greater_than(0))
    .verify_field("sales_channel", match_regex(r"[a-zA-Z0-9_\-]"))
)

trending_sales_metrics = semantic_view("trending_sales_metrics", trending_sales).schema(
    {
        "sale_count": metric_field(
            int64(),
            metric(
                Agg.COUNT,
                of=trending_sales.field("sale_id"),
                name="sale_count",
                description="Number of sale events.",
            ),
        ),
        "total_sales_usd": metric_field(
            float64(),
            metric(
                Agg.SUM,
                of=trending_sales.field("amount_usd"),
                name="total_sales_usd",
                description="Total sales amount in USD.",
            ),
        ),
    }
)
```

## Model details

| Method | Description |
| --- | --- |
| `.schema(dict)` | Storage agnostic definition of fields and types |
| `.description(str)` | Set model description |
| `.link(field, Predicate, url)` | Link a field to another model's attribute (similar to a foreign key) |
| `.link(Predicate, url)` | Link the whole model to a term |
| `.verify(verification_spec)` | Data quality rules at the model level |
| `.verify_field(field, check)` | Data quality rules at the field-level check (e.g. `greater_than(0)`) |
| `.sampling(method, limit)` | Define sampling method (`SamplingMethod.Random`, `.Head`, `.Disabled` — PascalCase members) |
| `.deprecated()` | Mark as deprecated |
| `.when(dependency)` | Define model dependencies for parallel execution |
| `.field(name)` | Return a field reference for `metric(of=model.field("column"))` |

## Semantic roles

Import semantic roles from `nxd.spec` and use them inside `.schema()` through
`field(...)` or tuple form:

```python
from nxd.spec import dimension, field, join, primary_key
from nxd.spec.data_types import int64, string

orders = semantic_model("orders").schema(
    {
        # primary_key() alone is not groupable — pair it with a dimension.
        "order_id": field(int64(), primary_key(), dimension(name="order_id", description="Order key.")),
        "status": field(
            string(),
            dimension(
                name="order_status",
                description="Order lifecycle state.",
            ),
        ),
        "customer_id": field(
            string(),
            join(to="customers", to_column="customer_id"),
        ),
    }
)
```

| Role | Meaning | Where to use it |
| --- | --- | --- |
| `primary_key()` | Entity key for one physical model row. Use multiple key fields for a composite key. **Pair it with a `dimension(...)` on the same field** — roles compose, and a key carrying only this role is not groupable, so no query can return which entity a row is about. | Physical `semantic_model` field |
| `dimension(name=None, pii=False, label=None, description="")` | Query concept that can be used for grouping and filtering. Put agent-visible dimension descriptions here. `pii=True` marks governed personal data. | Physical `semantic_model` field |
| `join(to, to_column=None, cardinality=None, to_data_product=None)` | Validated foreign-key edge to another semantic model. Declare it on the many-side field. | Physical `semantic_model` field |

`join(...)` defaults to many-to-one cardinality. Import `Cardinality` from
`nxd.spec` when the relationship needs an explicit cardinality value.

The `.schema()` dictionary accepts three equivalent field shapes:

```python
orders = semantic_model("orders").schema(
    {
        "order_id": field(int64(), primary_key(), dimension(name="order_id", description="Order key.")),
        "status": (
            string(),
            dimension(
                name="order_status",
                description="Order lifecycle state.",
            ),
        ),
        "amount_usd": float64(),
    }
)
```

Use source column names for schema keys. The logical `dimension(name=...)` is the
stable name used in semantic queries.

Put agent-visible descriptions on the semantic role: `dimension(description=...)`
or `metric(description=...)`. `field(description=...)`, `metric_field(description=...)`,
and tuple string descriptions become the physical `AttributeSpec` description;
they do not reach `describe_model`.

## Linking models

Use `.link()` with a `Predicate` to connect models across data products:

```python
from nxd.spec import Predicate

sales_model = (
    semantic_model("sales")
    .schema({"product_id": string()})
    .link("product_id", Predicate.SameAs,
          "/data-product/catalog#/models/products/attributes/product_id")
    .link(Predicate.GlossaryTerm,
          "/data-product/glossary#/terms/sales")
)
```

| Predicate | Meaning |
| --- | --- |
| `Predicate.SameAs` | Field is a foreign key to another model's attribute |
| `Predicate.GlossaryTerm` | Model or field maps to a glossary term |
| `Predicate.Derived` | Field is derived from another model's attribute |

## Metrics and semantic views

Metrics live on `semantic_view(...)`, not on base `semantic_model(...)` fields.
Register a view with `.model(view)` on the output; do not promise it as a
physical table. Custom SQL metrics use `Agg.EXPRESSION`, whose SQL is supplied
by the **port-level** `.model(view, expressions={...})` call.

`Agg.EXPRESSION` is only for a topology whose output **port** carries the
`expressions={...}` map — for example a warehouse-backed port registered by this
skill. It is not a derivation surface: do not use it to avoid materializing
row-level business rulings, classifications, date buckets, normalized values,
filtered defaults, row generation/removal, reusable ratio inputs, or column
arithmetic such as net revenue. Those belong in the transform as physical
columns or rows. It is also not a back door for unsupported metric kinds:
median/percentile-style metrics remain unsupported unless the product gains a
first-class aggregation for them. Generation paths that author a local closure
without a warehouse-backed port do not have this slot at all.

```python
from nxd.spec import Agg, data_product_output, metric, metric_field, semantic_view, storage
from nxd.spec.data_types import float64, int64

order_metrics = semantic_view("order_metrics", orders).schema(
    {
        "order_count": metric_field(
            int64(),
            metric(
                Agg.COUNT,
                of=orders.field("order_id"),
                name="order_count",
                description="Number of orders.",
            ),
        ),
        "total_revenue": metric_field(
            float64(),
            metric(
                Agg.SUM,
                of=orders.field("amount_usd"),
                name="total_revenue",
                description="Total order revenue.",
            ),
        ),
        "warehouse_revenue_sql": metric_field(
            float64(),
            metric(
                Agg.EXPRESSION,
                name="warehouse_revenue_sql",
                description="Warehouse-registered SQL SUM over order amount.",
            ),
        ),
    }
)

output = (
    data_product_output()
    # Validation requires at least one model at the output level.
    .model(order_metrics)
    .port(
        "warehouse",
        storage("/infra-profile/demo#/services/warehouse")
        # The expression map only persists here, on the PORT model.
        .model(
            order_metrics,
            expressions={"warehouse_revenue_sql": "SUM(amount_usd)"},
        )
        # Promises must be port-level; the storage driver never sees
        # output-level ones.
        .promise(orders),
    )
)
```

`metric(...)` parameters:

| Parameter | Description |
| --- | --- |
| `agg` | Aggregation from `Agg`: `COUNT`, `COUNT_DISTINCT`, `SUM`, `AVG`, `MIN`, `MAX`, `EXPRESSION` |
| `of` | Optional base field reference, usually `base_model.field("column")`. Omit it for `Agg.EXPRESSION`; the SQL expression names the fields. |
| `name` | Stable metric name used in semantic queries |
| `description` | Agent-visible metric description |
| `boolean` | Marks a boolean metric |
| `extra_dimensions` | Explicit additional dimensions that may slice the metric |
| `column` | Optional explicit aggregation column; mutually exclusive with `of`. Use `"*"` only for `COUNT(*)`. For `Agg.EXPRESSION`, omit both `of` and `column`; the SQL expression names the fields. |

A metric can be sliced by dimensions on its base model and by non-PII dimensions
reachable through validated many-to-one joins.

For `Agg.EXPRESSION`, the expression map key is the metric name, and the map
goes on the **port-level** `.model(...)` call — `storage(...).model(view,
expressions={...})`. Passing it to the output-level `.model(...)` is validated
and then discarded, so the metric compiles with no SQL behind it. In the example
above, `warehouse_revenue_sql` is authored on `order_metrics`, so the map rides
the `order_metrics` registration on the `warehouse` port.

A closure that needs net revenue (`amount_usd - discount_usd`) as a reusable
governed concept must instead derive a physical `net_revenue` column in the
transform and aggregate that column normally.

## Primitive types

Import from `nxd.spec.data_types`. Used in `.schema()` definitions.

| Function | Type |
| --- | --- |
| `string()` | String |
| `boolean()` | Boolean |
| `int8()`, `int16()`, `int32()`, `int64()` | Signed integers |
| `uint8()`, `uint16()`, `uint32()`, `uint64()` | Unsigned integers |
| `float16()`, `float32()`, `float64()` | Floating point |
| `double()` | Double precision float |
| `number()` | Generic number |
| `date()`, `date32()`, `date64()` | Date types |

## Complex types

| Function | Parameters | Type |
| --- | --- | --- |
| `timestamp(unit, timezone)` | `unit`: `DurationUnit.Milliseconds`, `.Seconds`, `.Microseconds`, `.Nanoseconds` | Timestamp |
| `decimal(precision, scale)` | e.g. `decimal(10, 2)` | Decimal128 |
| `binary(length)` | Optional fixed length | Binary |
| `vector()` | - | Vector |
| `vector_embeddings(dimensions)` | e.g. `vector_embeddings(1536)` | Embedding vector |
| `list(value_type)` | e.g. `list(string())` | List |
| `struct(fields)` | List of fields | Struct |
| `map(key_type, value_type)` | e.g. `map(string(), int64())` | Map |
| `dictionary(key_type, value_type)` | - | Dictionary encoded |
| `duration(unit)` | `DurationUnit` | Duration |
| `time32(unit)`, `time64(unit)` | `DurationUnit` | Time |

## Field verifiers

Import from `nxd.spec.validations`. Used with `.verify_field()` on semantic models.

| Function | Description |
| --- | --- |
| `greater_than(value)` | Field must be greater than value |
| `less_than(value)` | Field must be less than value |
| `greater_than_or_equal(value)` | Field must be >= value |
| `less_than_or_equal(value)` | Field must be <= value |
| `match_regex(pattern)` | Field must match regex pattern |

```python
from nxd.spec.validations import greater_than, match_regex

trending_sales = (
    semantic_model("trending_sales")
    .schema({"revenue": float64(), "currency_code": string()})
    .verify_field("revenue", greater_than(0))
    .verify_field("currency_code", match_regex(r"^[A-Z]{3}$"))
)
```
