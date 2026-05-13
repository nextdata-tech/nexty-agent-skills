# Data product spec

## Contents
- Data product (root constructor, builder methods)
- Inputs
  - Source-aligned inputs
  - Data product inputs
- Semantic models
- Transform (script, code, sql, remote)
- Triggers and scheduling (scheduled, updated, on_started, any_of, all_of)
- Outputs
  - Model output (data_product_output)
  - RPC output (data_product_rpc_output)
- Storage ports
- API ports
- Storage driver configurations
  - Object storage formats (SupportedFormat)
  - S3
  - ADLS
  - Databricks
  - Snowflake
  - Kafka
  - Pinecone
  - PgVector
- Data contracts
  - Schema contracts
  - Custom contracts
  - Quality checks (Soda, Great Expectations)
- Control (owner, data_product_access)
- Access approval
- Infrastructure references
  - Infra profile service URL
  - Data product output port URL
  - Glossary term URL
  - Model attribute URL
- Glossary

The data product DSL is the primary way to define data products. A `spec.py` file declares everything about a data product: its inputs, transform, outputs, models, contracts, and access policies.

Let's look at an example of a Spec file:

```
spec = (
    data_product(
        name="sales-influence-insights",
        domain="retail/sales",
        description="Sales Influence Insights uncovers...",
        version="0.1.1-dev",
        infra_profile="ecommerce-demo",
        source_repo_url="https://github.com/nextdata-tech/sales-influence-insights",
    )
    .transform(
        code(spark_transform)
        .when(
            any_of(
                updated("store-sales"),
                updated("pos-transactions"),
                scheduled("0 */8 * * *"),
            ),
            startup=True,
        )
        .compute("<instance-url>/infra-profile/ecommerce#/services/databricks-aws")
    )
    .input(
        "store-sales",
        data_product_input()
        .source("<instance-url>/data-product/store-sales#/output/port/adls/pos-sell-out")
        .expectation(
            custom("promotion_participation")
            .verify(code(expectation_store_sales.verify))
            .description("At least 90% of transactions ...")
        )
        .expectation(pos_sell_out),
    )
    .input(
        "pos-transactions",
        source_aligned_input()
            .source("<instance-url>/infra-profile/ecommerce#/services/nxd-s3")
            .model(pos_transactions)
            .config(s3_config(SupportedFormat.PARQUET).target_file("input/pos_transactions.parquet", pos_transactions))
    )
    .output(
        data_product_output()
        .port(
            "BI_on_snowflake",
            storage("<instance-url>/infra-profile/ecommerce#/services/snowflake-aws")
            .promise(trending_sales)
            .promise(
                quality(soda, "./contracts/trending_sales_checks.yaml")
                .model(trending_sales)
                .name("trending_sales_soda")
                .description("Soda data quality checks for trending_sales model")
            )
        )
        .port(
            "vector_embedding_pinecone",
            storage("<instance-url>/infra-profile/ecommerce#/services/pinecone").config(
                pinecone_config(
                    namespace="default",
                    region_name="us-east",
                )
            ),
        )
        .model(emerging_products)
        .access_approval(
            access_approval_config("<instance-url>/infra-profile/ecommerce#/services/servicenow")
        )
    )
    .output(
        data_product_rpc_output()
        .function(
            rpc_function(
                code(get_total_sold_by_channel),
                get_total_quantity_sold_by_channel_request,
                get_total_quantity_sold_by_channel_response,
            ).description("Total quantity sold by channel (online, store, wholesale, etc.)")
        )
        .port(
            "mcp-api",
            rpc_server("<instance-url>/infra-profile/ecommerce#/services/mcp-api")
            .enable_endpoints()
            .mcp_path("/mcp"),
        )
    )
    .link(
        Predicate.GlossaryTerm,
        "<instance-url>/data-product/demo/ecommerce-glossary#/terms/region/Europe",
    )
    .control("data-product-access", data_product_access().user("joe@nextdata.com"))
    .control("owner", owner().user("alice@nextdata.com"))
)
```

## Data product

`data_product()` is the root constructor. Every spec.py must call it and assign the result to `spec`.

| Parameter | Type | Description |
| --- | --- | --- |
| `name` | `str` | Kebab-case identifier (e.g. `"my-data-product"`) |
| `domain` | `str` | Slash-separated domain and subdomains (e.g. `"finance/payments"`) |
| `version` | `str` | Semver string (e.g. `"1.0.0-dev"`) |
| `description` | `str` | Human/AI-readable description |
| `infra_profile` | `str` | Name of the infra profile to use |
| `source_repo_url` | `str` | Optional URL to the source repository |

**Builder methods:**

| Method | Description |
| --- | --- |
| `.environment(name)` | Set deployment environment: dev/staging/prod |
| `.input(name, input_spec)` | Add a named input from other data products or external data assets (API, folder on S3, etc.) |
| `.transform(user_code_spec)` | Set the transform function: pandas, spark, SQL, dbt, asset bundles, etc. |
| `.output(output_spec)` | Add an output (can be called multiple times) |
| `.control(name, control_spec)` | Add owner or local access policies |
| `.link(predicate, url)` | Link the data product to a glossary term (e.g. `.link(Predicate.GlossaryTerm, url)`) |

## Inputs

Inputs declare where a data product reads data from. There are two types: source-aligned (from external storage) and data product (from an upstream data product).

See also: Creating data products

### Source-aligned inputs

Read directly from an external storage service (S3, ADLS, Snowflake, etc.).

```
spec = (
    data_product(...)
    .input(
        "pos-transactions",
        source_aligned_input()
        .source("<instance-url>/infra-profile/ecommerce#/services/nxd-s3")
        .model(pos_transactions)
        .config(s3_config(SupportedFormat.PARQUET).target_file("input/pos_transactions.parquet", pos_sell_out))
        .expectation(pos_transactions)
    )
)
```

| Method | Description |
| --- | --- |
| `.source(url)` | Infrastructure service URL |
| `.model(model)` | Associate a semantic model |
| `.config(storage_config)` | Set storage driver configuration |
| `.expectation(model_or_contract)` | Add an input data contract |
| `.environment(name)` | Set the upstream environment to read from |

### Data product inputs

Read from an upstream data product's output port.

```
spec = (
    data_product(...)
    .input(
        "store-sales",
        data_product_input()
        .source("<instance-url>/data-product/store-sales#/output/port/adls/pos-sell-out")
        .expectation(pos_sell_out)
        .environment("demo")
    )
)
```

| Method | Description |
| --- | --- |
| `.source(url)` | Data product output port URL |
| `.expectation(model_or_contract)` | Add an input data contract |
| `.environment(name)` | Set the upstream environment to read from |

## Semantic models

Semantic models define the schema and metadata of a data set. See Model spec for detailed documentation.

## Transform

The transform defines the processing logic of the data product. See also: Triggers

| Function | Description |
| --- | --- |
| `script(path)` | File-based transform (e.g. `script("transform.py")`) |
| `code(function)` | Inline function transform (e.g. `code(my_transform)`) |
| `sql(path_or_sql)` | SQL-based transform for Snowflake compute |
| `remote()` | Pre-deployed remote job (e.g. Databricks DAB job) |

**Builder methods** (available on all transform types):

| Method | Description |
| --- | --- |
| `.when(trigger, startup=bool)` | Set trigger condition |
| `.compute(url)` | Set compute infrastructure service URL |
| `.config(dict)` | Set driver-specific configuration (e.g. cluster settings) |

```
spec = (
    data_product(...)
    .transform(
        script("transform.py")
        .when(scheduled("0 */8 * * *"), startup=True)
        .compute("<instance-url>/infra-profile/ecommerce#/services/databricks-aws")
    )
)
```

## Triggers and scheduling

Triggers define when a data product's transform runs. See also: Triggers guide

Control when an individual transform runs using `.when(condition)` on `script()`, `code()`, or other transform types. Import conditions from `nxd.spec.conditions`:

| Function | Description |
| --- | --- |
| `scheduled(cron)` | Cron-based schedule (e.g. `"0 */6 * * *"`) |
| `updated(input_name)` | Triggered when the named input receives new data (from either an upstream data product or source-aligned dataset) |
| `on_started()` | Triggered when the data product first starts |
| `any_of(*triggers)` | OR — run when any trigger fires |
| `all_of(*triggers)` | AND — run when all triggers have fired |

```
from nxd.spec.conditions import scheduled, updated, any_of, all_of, on_started

# Run every 8 hours, or immediately on startup
.when(any_of(scheduled("0 */8 * * *"), on_started()))

# Run when both upstream product and source aligned input have updated
.when(all_of(updated("store-sales"), updated("wholesale-sales")))
```

## Outputs

Outputs declare how a data product publishes data to consumers.

### Model output

Publishes data models to storage ports. See also: Storage ports

```
spec = (
    data_product(...)
    .output(
        data_product_output()
        .model(trending_sales)
        .port(
            "BI_on_snowflake",
            storage("<instance-url>/infra-profile/ecommerce#/services/snowflake-aws").config(
                snowflake_config("RETAIL").target_table("TRENDING_SALES", trending_sales)
            ),
        )
        .port("s3", storage("<instance-url>/infra-profile/ecommerce#/services/nxd-s3").config(s3_config(SupportedFormat.PARQUET)))
        .promise(trending_sales)
    )
)
```

| Method | Description |
| --- | --- |
| `.model(model, is_public=True)` | Add a model to the output |
| `.port(name, storage_spec)` | Add a named storage port. Can be called multiple times |
| `.promise(model_or_contract)` | Add an output data contract |
| `.access_approval(config)` | Set access approval at the output level |
| `.managed_access()` | Enable platform-managed access |
| `.request_on_behalf_of(user)` | Set service principal identity for delegation |

### RPC output

Exposes functions as RPC endpoints, including via MCP. See also: MCP assistants, API ports

**Example:** This snippet implements the API output as an MCP (Model Context Protocol):

```
from nxd.spec import data_product_rpc_output, rpc_function, rpc_server

spec = (
    data_product(...)
    .output(
        data_product_rpc_output()
        .function(
            rpc_function(
                code(get_total_sold_by_channel),
                get_total_quantity_sold_by_channel_request,
                get_total_quantity_sold_by_channel_response,
            ).description("Total quantity sold by channel (online, store, wholesale, etc.)")
        )
        .port(
            "mcp-api",
            rpc_server("<instance-url>/infra-profile/ecommerce#/services/mcp-api")
            .enable_endpoints()
            .mcp_path("/mcp"),
        )
    )
)
```

| Method | Description |
| --- | --- |
| `.function(rpc_func)` | Add a callable function (defined with `rpc_function()`) |
| `.port(name, rpc_port)` | Add a named API port. Can be called multiple times |

## Storage ports

A storage port connects an output to a storage service. Created with `storage()`.

```
port = (
    storage("<instance-url>/infra-profile/ecommerce#/services/snowflake-aws")
    .config(snowflake_config("RETAIL").target_table("TRENDING_SALES", trending_sales))
    .promise(trending_sales)
    .managed_access()
)
```

| Method | Description |
| --- | --- |
| `.config(storage_config)` | Set storage driver configuration |
| `.model(model)` | Associate a model with this specific port |
| `.promise(model_or_contract)` | Add a port-level data contract |
| `.managed_access()` | Enable platform-managed access |
| `.access_approval(access_approval_spec)` | Set port-level access approval |
| `.access_control(config)` | Set port-level access control |
| `.enable_temporal_credentials()` | Enable temporal credentials (SAS tokens, pre-signed URLs) |
| `.disable_temporal_credentials()` | Disable temporal credentials |
| `.follow_approval_flow()` | Enable approval/ticketing workflows |
| `.skip_approval_flow()` | Skip approval/ticketing workflows |

## API ports

An API port exposes RPC functions over a network endpoint. Created with `rpc_server()`.

**Example:** This snippet implements the API output as an MCP (Model Context Protocol):

```
port = (
    rpc_server("<instance-url>/infra-profile/ecommerce#/services/mcp-api")
    .enable_endpoints()
    .mcp_path("/mcp")
)
```

| Method | Description |
| --- | --- |
| `.enable_endpoints()` | Enable the RPC endpoints |
| `.mcp_path(path)` | Set the MCP URL path (e.g. `"/mcp"`) |

The function exposed through the port is defined with `rpc_function()`:

| Function / Method | Description |
| --- | --- |
| `rpc_function(code_spec, request_model, response_model)` | Define a callable function with typed request/response models |
| `.description(str)` | Set a human-readable description of the function |

## Storage driver configurations

Each storage service has its own config function. See the Drivers section for driver-specific guides.

### Object storage formats

The `SupportedFormat` enum specifies file formats for object storage drivers (S3, ADLS):

| Value | Format |
| --- | --- |
| `SupportedFormat.CSV` | CSV |
| `SupportedFormat.JSON` | JSON |
| `SupportedFormat.PARQUET` | Parquet |
| `SupportedFormat.PDF` | PDF |

### S3

See also: S3 driver

```
from nxd.spec import s3_config, SupportedFormat

s3_config(SupportedFormat.PARQUET).target_file("output/trending_sales.parquet", trending_sales)
```

| Method | Description |
| --- | --- |
| `s3_config(file_type, bucket)` | Create S3 config. `file_type`: `SupportedFormat.CSV`, `.PARQUET`, `.JSON` |
| `.target_file(path, model)` | Set output file path and model |

### ADLS

See also: ADLS driver

```
from nxd.spec import adls_config, SupportedFormat

adls_config(SupportedFormat.PARQUET, container="retail").target_file("data/trending_sales.parquet", trending_sales)
```

| Method | Description |
| --- | --- |
| `adls_config(file_type, container)` | Create ADLS config |
| `.target_file(path, model)` | Set output file path and model |
| `.disable_temporal_credentials()` | Disable SAS tokens |
| `.follow_approval_flow()` | Enable approval workflows |
| `.request_on_behalf_of(name)` | Set service principal for delegation |

### Databricks

See also: Databricks driver

```
from nxd.spec import databricks_config

databricks_config(catalog="ecommerce", schema="retail").target_table("trending_sales", trending_sales)
```

| Method | Description |
| --- | --- |
| `databricks_config(catalog, schema)` | Create Databricks Unity Catalog config |
| `.target_table(table, model)` | Set target table and model |
| `.disable_promotion()` | Disable output promotion (for streaming) |

### Snowflake

See also: Snowflake driver

```
from nxd.spec import snowflake_config

snowflake_config(schema="RETAIL").target_table("TRENDING_SALES", trending_sales)
```

| Method | Description |
| --- | --- |
| `snowflake_config(schema)` | Create Snowflake config |
| `.target_table(table, model)` | Set target table and model |

### Kafka

See also: Kafka driver

```
from nxd.spec import kafka_config

kafka_config(topic="my-topic").group_id("my-group").starting_offsets("latest")
```

| Method | Description |
| --- | --- |
| `kafka_config(topic)` | Create Kafka config |
| `.group_id(id)` | Set consumer group ID |
| `.starting_offsets(offsets)` | Set starting offsets (e.g. `"latest"`) |

### Pinecone

```
from nxd.spec import pinecone_config

pinecone_config(namespace="my-ns", region_name="us-east-1")
```

### PgVector

```
from nxd.spec import pg_vector_config

pg_vector_config(schema="public")
```

## Data contracts

Data contracts validate data at input (expectations) and output (promises). See also: Transactions and contracts

### Schema contracts

Pass a semantic model directly to `.expectation()` or `.promise()` to validate the schema:

```
data_product_input().source(store_sales_dp_url).expectation(pos_sell_out)
data_product_output().port("BI_on_snowflake", storage(snowflake_service_url)).promise(trending_sales)
```

### Custom contracts

Use `custom()` to define verification logic with code or scripts:

```
from nxd.spec import custom, code, script

# Inline function verification
custom("promotion_participation").verify(
    code(expectation_store_sales.verify)
    .compute("<instance-url>/infra-profile/ecommerce#/services/databricks-aws")
).model(pos_sell_out)

# Script-based verification
custom("schema-check").script("contracts/promise.py").model(trending_sales)

# Verification with external service
custom("snowflake-check")
    .script("contracts/promise.py")
    .service(service_name="nxd-snowflake", driver="nxd:snowflake:1.0.0")
    .model(trending_sales)
```

| Method | Description |
| --- | --- |
| `custom(name)` | Create a named custom contract |
| `.verify(user_code_spec)` | Set verify function (`code()` or `script()`) |
| `.script(path)` | Shorthand to set a verify script file |
| `.service(service_name, driver)` | Add an external service for verification |
| `.model(model)` | Associate a model |
| `.description(str)` | Set description |

### Quality checks

Use third-party quality frameworks with `quality()`:

```
from nxd.spec import quality, soda, gx

# Soda checks
quality(soda, "./contracts/trending_sales_checks.yaml").name("trending_sales_soda").model(trending_sales)

# Great Expectations
quality(gx, "./contracts/trending_sales_gx.py").name("trending_sales_gx").model(trending_sales)
```

| Method | Description |
| --- | --- |
| `quality(tool, source)` | Create a quality check. `tool`: `soda` or `gx` |
| `.name(str)` | Set check name |
| `.description(str)` | Set description |
| `.model(model)` | Associate a model |

## Control

Controls defines the ownership and contacts of a data product. See also: Data access, Platform access

```
from nxd.spec import data_product_access, owner

spec = (
    data_product(...)
    .control("owner", owner().user("alice@nextdata.com").description("Sales Influence Insights"))
    .control("data-product-access", data_product_access().user("joe@nextdata.com").description("Retail analytics consumer"))
    .control("steward", data_product_access().user("bob@example.com").description("Data steward"))
)
```

| Function | Description |
| --- | --- |
| `owner()` | Ownership role |
| `data_product_access()` | General data product access |

All return a builder with `.user(email)` and `.description(str)`.

## Access approval

Configure approval workflows for accessing data product outputs.

```
from nxd.spec import access_approval_config

spec = (
    data_product(...)
    .output(
        data_product_output()
        .model(emerging_products, is_public=False)
        .port("BI_on_snowflake", storage("<instance-url>/infra-profile/ecommerce#/services/snowflake-aws").config(...))
        .access_approval(
            access_approval_config("<instance-url>/infra-profile/ecommerce#/services/servicenow")
            .approval_group("data-stewards")
        )
    )
)
```

| Function / Method | Description |
| --- | --- |
| `access_approval_config(url)` | Create approval config pointing to an approval service (Service now, Jira) |
| `.approval_group(name)` | Set the approval group |
| `.auto_approve()` | Enable automatic approval |
| `.requires_justification()` | Require justification text |
| `.timeout(timedelta)` | Set approval timeout |
| `.managed_access()` (on output/port) | Enable platform-managed temporal credentials |
| `.follow_approval_flow()` (on output/port) | Enable approval/ticketing |

## Infrastructure references

Infrastructure services, data product ports, and glossary terms are referenced by URL.

### Infra profile service URL

References a service defined in an infra profile:

```
<instance-url>/infra-profile/<profile-name>#/services/<service-name>
```

Used in: `.source()`, `.compute()`, `storage()`, `rpc_server()`

### Data product output port URL

References another data product's output port:

```
<instance-url>/data-product/<dp-name>#/output/port/<port-name>
```

Or with domain:

```
<instance-url>/data-product/<domain>/<dp-name>#/output/port/<port-name>
```

Used in: `data_product_input().source()`

### Glossary term URL

References a term in a glossary data product:

```
<instance-url>/data-product/<glossary-dp-name>#/terms/<term-name>
```

Used in: `.link(Predicate.GlossaryTerm, url)`

### Model attribute URL

References a specific attribute in another data product's model:

```
<instance-url>/data-product/<dp-name>#/models/<model-name>/attributes/<attribute-name>
```

Used in: `.link(field, Predicate.SameAs, url)`

## Glossary

Glossary data products define business terms. See also: Glossary data products

A glossary-only data product uses `.glossary()` instead of transforms:

```
spec = (
    data_product(
        name="finance-glossary",
        domain="finance",
        version="1.0.0-dev",
        description="Finance domain glossary",
        infra_profile="my-profile",
    )
    .glossary("glossary.yaml")
)
```

Other data products link to glossary terms using `.link()`:

```
trending_sales = (
    semantic_model("trending_sales")
    .schema({"revenue": float64()})
    .link(Predicate.GlossaryTerm, "<instance-url>/data-product/demo/ecommerce-glossary#/terms/revenue")
)
```
