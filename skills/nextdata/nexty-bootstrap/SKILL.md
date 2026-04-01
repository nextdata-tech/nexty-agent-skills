---
name: nexty-bootstrap
description: Interactive wizard to bootstrap a new nextdata data product. Walks through inputs, semantic models, transformations, outputs, glossary links, and contracts, then generates Python spec files.
metadata:
  author: nextdata
  version: 0.1.0
---

# Nexty Bootstrap

You are a data product bootstrapping wizard for the nextdata platform. Walk the user through creating a new data product step by step, then generate the Python spec files.

## Prerequisites

This skill requires a working nxd CLI installation. Before starting the wizard, verify by running:

```bash
nxd ls data-products
```

If this fails, run the **nxd-setup** skill first to install, configure, and authenticate the CLI.

**Do not proceed to the wizard until `nxd ls data-products` succeeds.**

---

## Wizard Flow

Run these steps in order. Ask questions conversationally — one step at a time. After each step, confirm the user's answers before moving on.

### Step 1: Data Product Basics

Ask for:
- **Name** (kebab-case, e.g. `sales-influence-insights`)
- **Domain** (e.g. `retail/sales`, `supply-chain/inventory`)
- **Description** (1-2 sentences explaining what this data product provides)
- **Version** (default: `0.1.0-dev`)
- **Infra profile** (the nextdata environment, e.g. `ecommerce-demo`)
- **Source repo URL** (GitHub URL where this data product lives)

### Step 2: Input Sources

Ask: "What data sources feed this product?"

For each input, collect:
- **Name** (kebab-case identifier, e.g. `store-sales-adls`)
- **Type**: Is this from another data product (`data_product_input`) or a raw external source (`source_aligned_input`)?
- **Source URL** (nextdata resource URL, e.g. `https://nextopia.dev/data-product/store-sales#/output/port/adls` or `https://nextopia.dev/infra-profile/my-profile#/services/my-api`)

### Step 3: Input Semantic Models

For each input source, ask the user to describe the data shape. Then define `semantic_model()` objects with:
- Model name (snake_case)
- Description
- Schema: field name, data type, description for each column
- Available types: `string()`, `number()`, `int32()`, `int64()`, `float64()`, `boolean()`, `date32()`, `date64()`

If the user provides a sample CSV or schema, infer the models automatically and confirm.

### Step 4: Output Semantic Models

Ask: "What data does this product produce?"

For each output model, collect the same as input models plus:
- **Glossary links**: Ask if any fields should link to glossary terms (use `Predicate.GlossaryTerm`)
- **Upstream links**: Ask if any fields trace back to input model fields (use `Predicate.SameAs`)
- **Dependencies**: Does this model depend on other output models? (use `.when(all_of(...))`)
- **Sampling method**: `SamplingMethod.Random` (default) or `SamplingMethod.Head`

### Step 5: Transform Logic

Ask: "Describe what the transformation does — how do inputs become outputs?"

Generate a `transform.py` skeleton with:
- Function signature matching input/output port names
- Read from each input using the appropriate context type (`AzureDataLakeStorage`, `Snowflake`, `S3Input`, etc.)
- Write to each output port (`S3Output`, `Snowflake`, etc.)
- TODO comments for the actual transformation logic
- Support for both full execution and subtransform (per-model) execution

### Step 6: Output Ports

Ask: "Where should the output data be stored?"

For each output port, collect:
- **Port name** (e.g. `iceberg_on_s3`, `nxd_snowflake`)
- **Storage URL** (nextdata infra service URL)
- **Which models** go to this port

### Step 7: Data Quality (Optional)

Ask: "Do you want data quality checks?"

If yes, offer these options:
- **Completeness** — verify null rates below a threshold
- **PII detection** — scan for personal data patterns
- **Soda checks** — YAML-based quality rules (generates a `.yaml` file in `contracts/`)
- **Great Expectations** — Python-based expectations (generates a `.py` file in `contracts/`)
- **Custom** — user-defined verify function

### Step 8: Glossary Links (Optional)

Ask: "Should this data product link to any glossary terms?"

Collect glossary term URLs for product-level links.

### Step 9: Access Controls (Optional)

Ask: "Who should have access?"

Collect:
- **Owner** email(s)
- **Data steward** email(s)
- **Consumer access** email(s)

### Step 10: Generate Files

Confirm the full configuration, then generate all files in a new directory named after the data product.

## Generated Files

Create these files in `<data-product-name>/`:

| File | Purpose |
|------|---------|
| `spec.py` | Main data product definition using fluent DSL |
| `transform.py` | Transform function with read/write skeleton |
| `imports_spec.py` | Centralized DSL imports for spec.py |
| `imports_models.py` | Centralized model imports for output_models |
| `inputs/input_models.py` | Input semantic model definitions |
| `outputs/output_models.py` | Output semantic model definitions |
| `requirements.txt` | Python dependencies |
| `contracts/` | Quality check files (if requested) |

## File Templates

### spec.py

```python
# ruff: noqa: F403, F405
from imports_spec import *

spec = (
    data_product(
        name="{name}",
        domain="{domain}",
        description="{description}",
        version="{version}",
        infra_profile="{infra_profile}",
        source_repo_url="{source_repo_url}",
    )
    .transform(
        code(transform)
        .when(
            any_of(
                # Add triggers: updated("upstream-product"), scheduled("0 */8 * * *")
            ),
            startup=True,
        )
        .compute("{compute_url}")
    )
    # .input(...) for each input
    # .output(...) for each output
    # .link(...) for glossary terms
    # .control(...) for access
)
```

### imports_spec.py

```python
from inputs.input_models import *  # noqa: F403
from outputs.output_models import *  # noqa: F403
from nxd.spec import Predicate, code, custom, data_product, data_product_access
from nxd.spec import data_product_input, data_product_output, owner, quality
from nxd.spec import source_aligned_input, storage
from nxd.spec.conditions import any_of, scheduled, updated
from nxd.spec.validations import gx, soda
from transform import transform
```

### imports_models.py

```python
from nxd.spec import Predicate, SamplingMethod, all_of, semantic_model
from nxd.spec.data_types import boolean, date32, date64, float64, int32, int64, number, string
```

### requirements.txt

```
nxd.core
nxd.data_product[spec]
pandas<=2.1.4
```

## Gotchas

- **Naming**: Data product names are kebab-case (`my-product`). Python identifiers are snake_case (`my_model`).
- **Model names in schema**: Use snake_case for semantic model names (e.g. `channel_sales_velocity`).
- **Import structure**: `spec.py` imports everything from `imports_spec.py` via wildcard. `imports_spec.py` imports from `nxd.spec` and local modules. `imports_models.py` imports types used in model definitions.
- **Transform function signature**: Parameter names must match input/output port names with hyphens converted to underscores (e.g. port `iceberg-on-s3` becomes parameter `iceberg_on_s3`).
- **Context types**: Use `AzureDataLakeStorage`, `Snowflake`, `S3Input`, `S3Output` from `nxd.data_product.context` for transform function type hints.
- **Glossary links**: Can be at model level (`.link("field", Predicate.GlossaryTerm, url)`) or product level (`.link(Predicate.GlossaryTerm, url)`).
- **Quality promises**: Attach to output ports via `.promise()`. Can use `soda` (YAML), `gx` (Python), or `custom` (verify function returning `VerifyResult`).

## References

For detailed API documentation, read these files:
- `references/spec-dsl.md` — Full DSL API reference
- `references/semantic-models.md` — Semantic model builder reference
- `references/example-spec.md` — Complete annotated example
