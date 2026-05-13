# Semantic models

## Contents
- Model details (builder methods)
- Linking models (Predicates)
- Primitive types
- Complex types
- Field verifiers

Let's start by looking at an example of a semantic model that will be used in the spec file:

```
trending_sales = (
    semantic_model("trending_sales")
    .sampling(method=SamplingMethod.Random)
    .description("Measures and compares the rate of sales growth per channel...")
    .schema({
            "product_id": (
                string(),
                "Identifier for the product whose sales velocity is being measured.",
            ),
            "sales_channel": (
                string(),
                "Sales channel from which transaction data was aggregated.",
            )
            ...
    })
    .link(
        "product_id",
        Predicate.SameAs,
        "/data-product/sales#/models/transactions/attributes/product_code",
    )
    .when(all_of(channel_sales_velocity, ...))
    .verify_field("product_id", greater_than(0))
    .verify_field("sales_channel", match_regex("[a-zA-Z0-9_\-]"))
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
| `.sampling(method, limit)` | Define sampling method (`SamplingMethod.RANDOM`, `.HEAD`, `.DISABLED`) |
| `.deprecated()` | Mark as deprecated |
| `.when(dependency)` | Define model dependencies for parallel execution |

## Linking models

Use `.link()` with a `Predicate` to connect models across data products:

```
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
| `vector()` | —   | Vector |
| `vector_embeddings(dimensions)` | e.g. `vector_embeddings(1536)` | Embedding vector |
| `list(value_type)` | e.g. `list(string())` | List |
| `struct(fields)` | List of fields | Struct |
| `map(key_type, value_type)` | e.g. `map(string(), int64())` | Map |
| `dictionary(key_type, value_type)` | —   | Dictionary encoded |
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

```
from nxd.spec.validations import greater_than, match_regex

trending_sales = (
    semantic_model("trending_sales")
    .schema({"revenue": float64(), "currency_code": string()})
    .verify_field("revenue", greater_than(0))
    .verify_field("currency_code", match_regex(r"^[A-Z]{3}$"))
)
```