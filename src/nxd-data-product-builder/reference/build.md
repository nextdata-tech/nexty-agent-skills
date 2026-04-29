# Creating data products

There are multiple experiences for data product development, from simply adding data sources to the mesh to authoring complex, customized data products. This guide provides and overview of the basics of data product development.

## Data product structure

Data products are a folder containing specific files defining the interface and behavior of the data product, for example:

```
data-product-name
├── .nxdignore
├── contracts
│   ├── expectation.py
│   └── promise.py
├── docs
│   └── readme.md
├── models.py
├── requirements.txt
├── spec.py
└── transform.py
```

This is an example of a data product performing a transformation (`transform.py`) in Python. Note that SQL transforms are also supported. The transform and all other aspect of the data product are specified using the Nextdata Python DSL, which is typically defined the `spec.py` Python module. This data product also supports custom verification of inputs and outputs via `expectation.py` and `promise.py` Python modules which specify data contracts. Custom verification may also utilize supported tools, such as Monte Carlo.

The key files are:

*   `.nxdignore` : specify files and directories to exclude from the data product bundle when building and deploying.
*   `models.py` : specify the various models and their attributes for validation by the mesh.
*   `requirements.txt` : specify the Python dependencies required by the data product, which will be installed in the data product's execution environment.
*   `spec.py` : specifies the data product identifiers, transform logic, inputs and outputs, semantic models, contracts, access policies and more.
*   `transform.py` : defines the transformation code of the data product.

For a more detailed definition of the interfaces of the various Python modules and supporting API and libraries, see the Python Data Product Spec DSL.

### Excluding files

When building and deploying data products, you may want to exclude certain files from being included in the bundle. NXD supports a `.nxdignore` file that works similar to `.gitignore` and `.dockerignore`. This gives you explicit control over what gets included in your bundle.

`.nxdignore` example:

```
# Version control
.git/**
.svn/**
.hg/**
# IDE and editor files
.vscode/**
.idea/**
*.swp
*.swo
*~
# OS files
.DS_Store
Thumbs.db
# Build artifacts
target/**
build/**
dist/**
*.log
# Temporary files
*.tmp
*.temp
# Node modules
node_modules/**
# Python cache
__pycache__/**
*.pyc
*.pyo
.pytest_cache/**

# Also supports negation patterns
# !keep-this.tmp
```

`.nxdignore` syntax:

*   One pattern per line
*   Lines starting with `#` are comments and ignored
*   Empty lines are ignored
*   Supports glob patterns like `*.txt`, `**/*.log`, etc.
*   Patterns are relative to the data product directory
*   Use `!pattern` to include files that would otherwise be excluded (negation patterns)

**Important**: NXD does not apply any default exclusions. All exclusions must be explicitly specified in your `.nxdignore` file, giving you complete control over what gets included in your data product bundle. We recommend including common patterns like version control directories, build artifacts, and cache files as shown in the example above.

### Third-party package imports

Your transform code can import third-party packages (e.g., `pandas`, `pyspark`) that aren't installed locally. The CLI automatically stubs these imports during spec parsing so your data product can be built without installing all dependencies locally.

To allow specific packages through the sandbox (e.g., if you need them to be actually imported during spec parsing), set `NXD_SANDBOX_ALLOWLIST` to a comma-separated list of package names:

```
NXD_SANDBOX_ALLOWLIST=pandas,numpy nxd launch
```

To disable the sandbox entirely for debugging, set `NXD_DISABLE_IMPORT_SANDBOX=1`.

## Data product evolution

Data products are not static; over their lifetime, they change and evolve. To ensure stability and predictability for downstream consumers, certain rules and best practices apply.

### Semantic model

Semantic models describe the structure and meaning of data entities within your system.  
They define the expected schema (attributes, types, and relationships).

For example, a `trending_sales` semantic model might define attributes like `product_id`, `region`, `sales_channel` and `velocity_score` with their respective data types and descriptions.

```
from nxd.spec import semantic_model
from nxd.spec.data_types import float64, string

trending_sales_model = (
    semantic_model("trending_sales")
    .description("Rate of sales growth per channel per region")
    .schema(
        {
            "product_id":     (string(), "Product identifier"),
            "region":         (string(), "Region where the sale occurred"),
            "sales_channel":  (string(), "Sales channel that made the sale"),
            "velocity_score": (float64(), "Sales velocity score"),
        }
    )
    .deprecated()
)
```

| Functions | Description |
| --- | --- |
| **`semantic_model("trending_sales")`** | Creates a new semantic model named `trending_sales`. The name must be unique within your project. |
| **`.description({...})`** | Provides a human-readable description of the model’s purpose. Useful for documentation and discovery. |
| **`.schema({...})`** | Defines the schema of the model as a dictionary mapping field names to data types. |
| **`.sampling({...})`** | Define the sampling method for this semantic model. |
| **`.link({...})`** | Link a field in this model to an attribute in another data product/model using a predicate. |
| **`.verify({...})`** | Add a user-defined verification check to this semantic model. |
| **`.verify_field({...})`** | Add a field-specific verification check to this semantic model. |
| **`.document_collection()`** | Mark the model as representing the metadata of a collection of documents |
| **`.deprecated()`** | Marks the model as deprecated. Use this to indicate that the model should no longer be used but is retained for backward compatibility. |

#### Semantic model changes

In the current version of **Nextdata OS**, semantic models are treated as **immutable**. This design choice simplifies compatibility for all downstream consumers of a data product.

As a result, data product developers:

*   **Can** add new semantic models.
*   **Can** mark existing semantic models as _deprecated_.
*   **Cannot** modify or remove existing semantic models.

> **Note:** Future versions of Nextdata OS will provide more advanced support for semantic model evolution, including controlled modifications and migration strategies. See Model versioning for more details.

# Triggers

Data products give teams a simple way to run and connect their work without relying on one big, central pipeline. Each product runs on its own, knows when to trigger, and clearly expresses its dependencies.

*   **Independent but connected**: Each data product can listen for events, run on a schedule, or both. The bigger workflow appears naturally, based on how products depend on one another. No giant DAG to manage.
*   **Everything in code**: Logic, schedules, tests, and contracts all live in code. Developers can run things locally, test with mocks, and ship changes through normal Git and CI/CD. Code reviews look and feel like any other software project.
*   **Clarity and trust**: You can see lineage across teams, track freshness, and know exactly what updated, when, and by what. Data is treated like a real product, not a side-effect of pipelines.

This approach makes orchestration easier to manage, easier to trust, and easier to scale across teams.

### Event-driven triggers

Here is an example of configuration from an "off-mesh" data asset on S3:

```
  spec = (
      data_product()
      .input("my_source",
          source_aligned_input()
          .source("service://mesh-name/infra-profile/s3-service-name")
          .update_trigger(
              object_storage_data_trigger()  # Triggers when new data arrives
          )
      )
  )
```

### Schedule-based triggers

Here is an example of a data product with a cron based schedule.

```
  spec = (
      data_product(name="my-data-product")
      .global_trigger(
          ScheduleTrigger(cron_schedule="0 2 * * *")  # Run daily at 2 AM
      )
      .input("raw_data",
          source_aligned_input()
          .source("service://demo/default/my-database")
      )
      .output(
          data_product_output()
          .port("processed", storage("service://demo/default/my-storage"))
      )
      .transform(code(my_transform_function))
  )
```

### Combining event-driven and schedule-based orchestration

You can also mix-and-match these with conditional statements:

```
spec = (
      data_product(name="my-data-product")
      .input("upstream_orders",
          data_product_input()
          .source("https://nextdata.com/data-product/orders#/output/snowflake")
      )
      .input("raw_inventory",
          source_aligned_input()
          .source("service://demo/default/inventory-db")
          .update_trigger(table_storage_data_trigger())  # Triggers on new data arrival
      )
      .output(
          data_product_output()
          .port("analytics", storage("service://demo/default/warehouse"))
      )
      .transform(
          code(my_transform_function)
          .when(
              either(
                  updated("orders"),           # Trigger when upstream orders data product updates
                  scheduled("0 6 * * *"),     # OR trigger daily at 6 AM
                  updated("raw_inventory")     # OR trigger when raw_inventory input gets new data
              )
          )
      )
  )
```

# Unstructured data (beta)

Unstructured semantic models are still in beta.

This guide shows you how to build data products that process unstructured data on the Nextdata platform.

## Overview

The Nextdata platform provides:

*   Unified abstraction over structured and unstructured data
*   Choice of extraction tools (Unstructured, LlamaIndex, custom parsers)
*   Multi-modal output ports for different downstream consumers

## Define your semantic model

```
product_unified = (
    semantic_model("product_unified")
    .sampling(method=SamplingMethod.Random)
    .description("Product data combining structured, image, and PDF sources.")
    .schema({
        "product_id": (string(), "Unique product identifier."),
        ...
        "document_specs": (json(), "PDF-extracted specs and instructions."),
        "enriched_description": (string(), "Combined description from all sources."),
        "s3_asset_path": (string(), "S3 path for assets."),
        "image_url_patter": (string(), "Path of the image assets.")
    })
    .verify_field("stock_quantity", between(0, 999999))
    .verify_field("quality_score", between(0, 1))
    .verify(code(null_rate_above_threshold))
    .verify(code(check_text_sentiment_quality))
    .verify(code(check_pii_compliance_on_pdfs))
    .verify(code(check_image_extraction_completeness))
)
```

## Define your data product

Create a `spec.py` file that defines inputs from both structured and unstructured sources:

```
spec = (...)
    .input(
        "raw_documents",
        source_aligned_input()
        .source("https://your-domain/infra/services/s3-documents")
        .config(s3_config(
            bucket="document-store",
            prefix="raw/",
        ))
    )
    .input(
        "customer_data",
        data_product_input()
        .source("https://your-domain/data-products/customers#/output/port/snowflake")
    )
    .transform(code(process_documents))
    .output(...)
)
```

### Multimodal outputs

The same semantic models can be served over different output ports:

```
spec = (
    data_product(...)
    .intput(...)
    .transform(...)
    .output(
        data_product_output()
        # Analytics output
        .port("analytics", storage("snowflake"))
        # ML feature store
        .port("features", storage("s3"))
        # Vector database for RAG
        .port("vectors", storage("pinecone"))
    )
)
```

# Multimodal outputs

This guide shows you how to serve data for different use cases .

## Analytics

Below is an example of how to specify a data warehouse (e.g. Snowflake) for analytics use cases. You can swap out the torage configuration for any other data warehouse or lakehouse (e.g. BigQuery, Databricks, Trino, Dremio, etc.) and the pattern would be the same.

```
spec = (
    data_product(...)
    .transform(...)
    .output(
        data_product_output()
        .port(
            "BI_on_snowflake",
            storage("https://nextopia.dev/infra-profile/ecommerce-demo#/services/nxd-snowflake-aws")
        )
)
```

## Machine learning

Below is an example of how to specify object storage (e.g. S3) for machine learning use cases. You can swap out the storage configuration for any other object storage (e.g. ADLS) and the pattern would be the same.

```
spec = (
    data_product(...)
    .transform(...)
    .output(
        data_product_output()
        .port(
            "iceberg_on_s3",
            storage("https://nextopia.dev/infra-profile/ecommerce-demo#/services/s3-output")
            ...
        )
)
```

## RAG

Below is an example of how to specify a vector database (e.g. Pinecone) for RAG use cases. You can swap out the storage configuration for any other vector database and the pattern would be the same.

```
spec = (
    data_product(...)
    .transform(...)
    .output(
        data_product_output()
        .port(
            "vector_embedding_pinecone",
            storage("https://nextopia.dev/infra-profile/ecommerce-demo#/services/nxd-pinecone")
            .config(pinecone_config(
                    namespace="default",
                    region_name="us-east")
            )
        )
)
```

## AI agents

Below is an example of how to specify an API function (e.g., MCP) for agents to call.

```
spec = (
    data_product(...)
    .transform(...)
    .output(
        data_product_output()
        .function(
            rpc_function(code(get_total_quantity_sold_by_channel)).description(
                "get_total_quantity_sold_by_channel"
            )
        )
        .port(
            "mcp-api",
            rpc_server(
                "https://nextopia.dev/infra-profile/ecommerce-demo#/services/mcp-api-service-k8s"
            )
            .enable_endpoints()
            .mcp_path("/mcp"),
        )
    )
)
```
