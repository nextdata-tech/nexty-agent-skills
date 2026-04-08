# Semantic Models Reference

## Builder: `semantic_model()`

```python
from nxd.spec import Predicate, SamplingMethod, all_of, semantic_model
from nxd.spec.data_types import string, number, int32, int64, float64, boolean, date32, date64
```

## Basic Model

```python
my_model = (
    semantic_model("model_name")  # snake_case name
    .description("What this model represents.")
    .schema({
        "field_name": (data_type(), "Field description."),
    })
)
```

## Full Model with All Options

```python
my_model = (
    semantic_model("channel_sales_velocity")
    .sampling(method=SamplingMethod.Random)
    .description("Measures rate of sales growth per channel.")
    .schema({
        "product_id": (string(), "Product identifier."),
        "sales_channel": (string(), "Channel the data was aggregated from."),
        "region": (string(), "Region of sales activity."),
        "velocity_score": (float64(), "Normalized velocity score."),
        "units_sold": (int32(), "Units sold in period."),
        "is_active": (boolean(), "Whether product is actively sold."),
        "sale_date": (date32(), "Date of most recent sale."),
        "revenue": (float64(), "Total revenue in period."),
    })
    # Link field to same attribute in upstream model
    .link(
        "product_id",
        Predicate.SameAs,
        "https://nextopia.dev/data-product/demo/product-catalog#/models/product_catalog/attributes/product_code",
    )
    # Link field to glossary term
    .link(
        "sales_channel",
        Predicate.GlossaryTerm,
        "https://app.demo.trynxd.com/data-product/demo/ecommerce-glossary#/terms/sales_channel",
    )
    # Model-level glossary link (no field specified)
    .link(
        Predicate.GlossaryTerm,
        "https://app.demo.trynxd.com/data-product/demo/ecommerce-glossary#/terms/trending_sales",
    )
    # Declare dependencies on other models
    .when(all_of(other_model_a, other_model_b))
    # Mark a field as encrypted
    .encrypted("product_id")
)
```

## Data Types

| Type | Import | Description |
|------|--------|-------------|
| `string()` | `from nxd.spec.data_types import string` | Text/varchar |
| `number()` | `from nxd.spec.data_types import number` | Generic number |
| `int32()` | `from nxd.spec.data_types import int32` | 32-bit integer |
| `int64()` | `from nxd.spec.data_types import int64` | 64-bit integer |
| `float64()` | `from nxd.spec.data_types import float64` | 64-bit float |
| `boolean()` | `from nxd.spec.data_types import boolean` | True/false |
| `date32()` | `from nxd.spec.data_types import date32` | Date (no time) |
| `date64()` | `from nxd.spec.data_types import date64` | Date with time (ISO8601) |

## Sampling Methods

| Method | Use when |
|--------|----------|
| `SamplingMethod.Random` | Default. Good for large, uniform datasets |
| `SamplingMethod.Head` | When order matters or you want first N rows |

## Predicates for Links

| Predicate | Use when |
|-----------|----------|
| `Predicate.SameAs` | Field traces to same attribute in another model (data lineage) |
| `Predicate.GlossaryTerm` | Field maps to a business glossary term |

## Link Formats

**Field-level link** (3 args): `.link("field_name", Predicate, "url")`

**Model-level link** (2 args): `.link(Predicate, "url")`

## URL Patterns

### Upstream model attribute
```
https://nextopia.dev/data-product/{domain}/{product}#/models/{model}/attributes/{attribute}
```

### Glossary term
```
https://app.demo.trynxd.com/data-product/{domain}/{glossary-product}#/terms/{term}
```

## Organizing Models

**Input models** go in `inputs/input_models.py` — these define the expected schema of incoming data.

**Output models** go in `outputs/output_models.py` — these define what the data product produces.

Import all model types in `imports_models.py`:

```python
from nxd.spec import Predicate, SamplingMethod, all_of, semantic_model
from nxd.spec.data_types import boolean, date32, date64, float64, int32, int64, number, string
```
