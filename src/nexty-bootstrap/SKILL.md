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

### Step 1: Where do you want to start?

Ask: "Where is the data for this product coming from?" and present three options:

#### Option A: Existing data

The user has data they want to turn into a data product.

Ask: "Is the data available locally, or is it in a remote service?"

**Local data**: Ask for the file path (relative or absolute). Read the file (CSV, Parquet, JSON, etc.) and infer the schema — column names, types, and sample values. Use this to auto-generate input semantic models. Confirm with the user.

**Remote data (S3, Snowflake, ADLS, Databricks)**: For v1, help the user manually download a sample or get metadata so we can understand the data shape. Walk them through it:

- **S3**: Ask for the bucket name and folder/key path. Guide them:
  ```bash
  aws s3 cp s3://<bucket>/<path>/sample.csv ./sample-data/
  ```
  Then read the downloaded file to infer the schema.

- **Snowflake**: Ask for the database, schema, and table name. Guide them:
  ```bash
  # Using snowsql or the Snowflake CLI
  snowsql -q "DESCRIBE TABLE <database>.<schema>.<table>"
  # Or to get a sample:
  snowsql -q "SELECT * FROM <database>.<schema>.<table> LIMIT 10" -o output_format=csv -o output_file=sample-data/sample.csv
  ```
  Then use the DESCRIBE output or sample to infer the schema.

- **ADLS**: Ask for the storage account, container, and blob path. Guide them:
  ```bash
  az storage blob download --account-name <account> --container-name <container> --name <path> --file ./sample-data/sample.csv
  ```

- **Databricks**: Ask for the catalog, schema, and table name. Guide them:
  ```bash
  databricks sql execute --statement "DESCRIBE TABLE <catalog>.<schema>.<table>"
  # Or for a sample:
  databricks sql execute --statement "SELECT * FROM <catalog>.<schema>.<table> LIMIT 10"
  ```

After obtaining the data or metadata, infer the schema and auto-generate input semantic models. Confirm with the user.

#### Option B: Existing source code

The user has transformation code they want to wrap as a data product.

Ask for the relative path to the codebase. Read the source code to understand:
- What data it reads (inputs) and from where
- What transformations it performs
- What data it produces (outputs)
- Any existing schema definitions

Use this analysis to pre-populate the input models, output models, and transform skeleton. Confirm with the user.

#### Option C: Other data products

The user wants to build on top of existing nextdata data products.

Run:
```bash
nxd ls data-products
```

Show the list and ask the user to select which data products to use as inputs. For each selected product, the generated `spec.py` will use `data_product_input().source(...)` pointing to that product's output port.

If the product has published semantic models, use those as the input model definitions. Otherwise, ask the user to describe the expected schema.

---

The user can combine options — e.g. "I have local CSV data AND I want to consume from another data product." Handle this naturally by collecting inputs from multiple sources.

### Step 2: Data Product Basics

Based on the previous step, suggest ideas for all the below:
- **Name** (kebab-case, e.g. `sales-influence-insights`)
- **Domain** (e.g. `retail/sales`, `supply-chain/inventory`)
- **Description** (1-2 sentences explaining what this data product provides)
- **Version** (default: `0.1.0-dev`)
- **Infra profile** (the nextdata environment, e.g. `ecommerce-demo`)
- **Source repo URL** (GitHub URL where this data product lives)

Have the user confirm or edit them.

### Step 3: Input Sources & Semantic Models

Based on Step 1, you should already have a good understanding of the input data shape.

For each input source, finalize:
- **Input name** (kebab-case identifier, e.g. `store-sales-adls`)
- **Input type**: `data_product_input` (from another data product) or `source_aligned_input` (raw/external source)
- **Source URL** (nextdata resource URL)
- **Semantic model**: `semantic_model()` with name (snake_case), description, and schema with field names, data types, and descriptions
- Available types: `string()`, `number()`, `int32()`, `int64()`, `float64()`, `boolean()`, `date32()`, `date64()`

If you inferred models from data/code in Step 1, present them for confirmation. Let the user adjust field names, types, or descriptions.

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

For real-world examples, clone or browse the public examples repo:

```bash
git clone https://github.com/nextdata-tech/nextdata-public-examples.git
```

Each directory under `data_products/` is a complete data product (spec.py, transform.py, models, etc.). Use these as reference when generating files — pick the example closest to what the user is building.
