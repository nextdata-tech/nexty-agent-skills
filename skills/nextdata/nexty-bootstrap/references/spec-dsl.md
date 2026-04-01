# nextdata Spec DSL Reference

## Core Builder: `data_product()`

```python
from nxd.spec import data_product

spec = data_product(
    name="my-data-product",        # kebab-case, required
    domain="retail/sales",          # slash-separated domain path
    description="What it does.",    # 1-2 sentences
    version="0.1.0-dev",           # semver
    infra_profile="my-profile",    # nextdata infra profile name
    source_repo_url="https://...", # GitHub URL
)
```

## `.transform()`

Defines the transformation logic.

```python
from nxd.spec import code
from nxd.spec.conditions import any_of, updated, scheduled

.transform(
    code(transform_function)
    .when(
        any_of(
            updated("upstream-data-product"),
            scheduled("0 */8 * * *"),  # cron expression
        ),
        startup=True,  # run on deploy
    )
    .compute("https://nextopia.dev/infra-profile/my-profile#/services/k8s-compute")
    .config({
        "resources": {
            "requests": {"memory": "768Mi", "cpu": "500m"},
            "limits": {"memory": "2Gi", "cpu": "500m"},
        },
    })
)
```

### Trigger Conditions

| Function | Description |
|----------|-------------|
| `updated("product-name")` | Fires when upstream product updates |
| `scheduled("cron-expr")` | Fires on cron schedule |
| `any_of(...)` | Fires when any condition matches |
| `all_of(...)` | Fires when all conditions match |

## `.input()`

Defines an input data source.

```python
from nxd.spec import data_product_input, source_aligned_input, custom, code

# From another data product
.input(
    "store-sales-adls",  # input name (kebab-case)
    data_product_input().source("https://nextopia.dev/data-product/store-sales#/output/port/adls"),
)

# From a raw external source
.input(
    "twitter",
    source_aligned_input().source("https://nextopia.dev/infra-profile/my-profile#/services/twitter-api"),
)

# With expectations
.input(
    "online-sales",
    data_product_input().source("https://nextopia.dev/data-product/online-sales#/output/port/s3"),
    .expectation(
        custom("daily_freshness")
        .verify(code(my_verify_function))
        .description("Ensures data is from today")
    ),
)
```

### Input Types

| Type | When to use |
|------|------------|
| `data_product_input()` | Consuming from another nextdata data product |
| `source_aligned_input()` | Consuming from a raw/external data source |

## `.output()`

### Data Output

```python
from nxd.spec import data_product_output, storage, quality, custom, code
from nxd.spec.validations import soda, gx

.output(
    data_product_output()
    .port(
        "iceberg_on_s3",
        storage("https://nextopia.dev/infra-profile/my-profile#/services/s3-output")
        .promise(my_model)              # model-level promise (schema contract)
        .promise(
            quality(soda, "./contracts/checks.yaml")
            .model(my_model)
            .name("soda_checks")
            .description("Soda data quality checks")
        )
        .promise(
            quality(gx, "./contracts/validations.py")
            .model(my_model)
            .name("gx_validations")
            .description("Great Expectations validations")
        )
        .promise(
            custom("completeness")
            .model(my_model)
            .description("Null rate below 10%")
            .verify(code(completeness_verify))
        ),
    )
    .port(
        "nxd_snowflake",
        storage("https://nextopia.dev/infra-profile/my-profile#/services/nxd-snowflake")
        .promise(my_model),
    )
    .model(my_output_model)  # register models with the output
    .access_approval(
        access_approval_config("https://nextopia.dev/infra-profile/my-profile#/services/approval")
    )
)
```

### RPC Output

```python
from nxd.spec import data_product_rpc_output, rpc_function, rpc_server, code

.output(
    data_product_rpc_output()
    .function(
        rpc_function(
            code(my_rpc_function),
            request_model,
            response_model,
        ).description("What this function does")
    )
    .port(
        "mcp-api",
        rpc_server("https://nextopia.dev/infra-profile/my-profile#/services/mcp-api")
        .enable_endpoints()
        .mcp_path("/mcp"),
    )
)
```

### Storage Configs

```python
from nxd.spec import pinecone_config, snowflake_config

# Pinecone vector store
storage(url).config(pinecone_config(namespace="default", region_name="us-east"))

# Snowflake
storage(url).config(snowflake_config(...))
```

## `.link()`

Links the data product to glossary terms or upstream attributes.

```python
from nxd.spec import Predicate

# Product-level glossary link
.link(Predicate.GlossaryTerm, "https://app.demo.trynxd.com/data-product/demo/glossary#/terms/sales_channel")
```

## `.control()`

Defines access controls.

```python
from nxd.spec import data_product_access, owner

.control("owner", owner().user("user@company.com"))
.control("data-product-access", data_product_access().user("consumer@company.com"))
.control("steward", data_product_access().user("steward@company.com"))
```

## `.documentation()`

Links to documentation.

```python
.documentation("docs/readme.ipynb")
```

## All Imports from `nxd.spec`

```python
from nxd.spec import (
    Predicate,
    SamplingMethod,
    access_approval_config,
    all_of,
    code,
    custom,
    data_product,
    data_product_access,
    data_product_input,
    data_product_output,
    data_product_rpc_output,
    owner,
    pinecone_config,
    quality,
    rpc_function,
    rpc_server,
    semantic_model,
    snowflake_config,
    source_aligned_input,
    storage,
)
from nxd.spec.conditions import any_of, scheduled, updated
from nxd.spec.data_types import boolean, date32, date64, float64, int32, int64, number, string
from nxd.spec.validations import gx, soda
```
