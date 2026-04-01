# Example: Complete Data Product

A simplified data product that reads sales data from S3, computes velocity metrics, and writes to Snowflake and S3.

## File Structure

```
sales-velocity/
├── spec.py
├── transform.py
├── imports_spec.py
├── imports_models.py
├── requirements.txt
├── inputs/
│   └── input_models.py
├── outputs/
│   └── output_models.py
└── contracts/
    └── completeness.py
```

## inputs/input_models.py

```python
from imports_models import *  # noqa: F403

sales_transactions = (
    semantic_model("sales_transactions")
    .sampling(method=SamplingMethod.Head)
    .description("Raw transactional sales data across all channels and regions.")
    .schema({
        "sale_id": (number(), "Unique identifier for each sale."),
        "product_id": (number(), "Unique identifier for the product sold."),
        "quantity": (number(), "Quantity of the product sold."),
        "sale_amount": (number(), "Total amount of the sale."),
        "sale_date": (string(), "Date of the sale."),
        "channel_id": (string(), "Sales channel identifier."),
    })
)
```

## outputs/output_models.py

```python
from imports_models import *  # noqa: F403

channel_sales_velocity = (
    semantic_model("channel_sales_velocity")
    .sampling(method=SamplingMethod.Random)
    .description("Measures rate of sales growth per channel.")
    .schema({
        "product_id": (string(), "Product identifier."),
        "sales_channel": (string(), "Sales channel."),
        "region": (string(), "Region of sales activity."),
        "velocity_score": (float64(), "Normalized velocity score."),
        "units_sold_last_7_days": (int32(), "Units sold last 7 days."),
        "sales_change_percent": (float64(), "Percent change in units sold."),
        "sales_trend": (string(), "Trend direction: increasing, decreasing, stable."),
    })
    .link(
        "product_id",
        Predicate.GlossaryTerm,
        "https://app.demo.trynxd.com/data-product/demo/ecommerce-glossary#/terms/product_id",
    )
)
```

## imports_models.py

```python
from nxd.spec import Predicate, SamplingMethod, all_of, semantic_model
from nxd.spec.data_types import boolean, date32, date64, float64, int32, int64, number, string

__all__ = [
    "Predicate", "SamplingMethod", "all_of", "semantic_model",
    "boolean", "date32", "date64", "float64", "int32", "int64", "number", "string",
]
```

## imports_spec.py

```python
from inputs.input_models import sales_transactions
from nxd.spec import Predicate, code, custom, data_product, data_product_access
from nxd.spec import data_product_input, data_product_output, owner, quality, storage
from nxd.spec.conditions import any_of, scheduled, updated
from nxd.spec.validations import soda
from outputs.output_models import channel_sales_velocity
from transform import transform
from contracts import completeness

__all__ = [
    "sales_transactions", "channel_sales_velocity", "transform", "completeness",
    "Predicate", "code", "custom", "data_product", "data_product_access",
    "data_product_input", "data_product_output", "owner", "quality", "storage",
    "any_of", "scheduled", "updated", "soda",
]
```

## spec.py

```python
# ruff: noqa: F403, F405
from imports_spec import *

spec = (
    data_product(
        name="sales-velocity",
        domain="retail/sales",
        description="Computes sales velocity metrics per channel and region from raw transaction data.",
        version="0.1.0-dev",
        infra_profile="ecommerce-demo",
        source_repo_url="https://github.com/my-org/sales-velocity",
    )
    .transform(
        code(transform)
        .when(
            any_of(
                updated("online-sales"),
                scheduled("0 */8 * * *"),
            ),
            startup=True,
        )
        .compute("https://nextopia.dev/infra-profile/ecommerce-demo#/services/k8s-compute")
    )
    .input(
        "online-sales",
        data_product_input().source("https://nextopia.dev/data-product/online-sales#/output/port/s3"),
    )
    .output(
        data_product_output()
        .port(
            "nxd_snowflake",
            storage("https://nextopia.dev/infra-profile/ecommerce-demo#/services/nxd-snowflake")
            .promise(channel_sales_velocity),
        )
        .port(
            "iceberg_on_s3",
            storage("https://nextopia.dev/infra-profile/ecommerce-demo#/services/s3-output")
            .promise(channel_sales_velocity)
            .promise(
                custom("completeness")
                .model(channel_sales_velocity)
                .description("Ensures completeness of output is at least 90%")
                .verify(code(completeness.verify))
            ),
        )
        .model(channel_sales_velocity)
    )
    .link(
        Predicate.GlossaryTerm,
        "https://app.demo.trynxd.com/data-product/demo/ecommerce-glossary#/terms/sales_channel",
    )
    .control("owner", owner().user("hello@nextdata.com"))
    .control("data-product-access", data_product_access().user("consumer@nextdata.com"))
)
```

## transform.py

```python
import logging

import pandas as pd
from nxd.core.context import ExecutionContext
from nxd.data_product.context import S3Input, S3Output, Snowflake
from outputs.output_models import channel_sales_velocity

_logger = logging.getLogger("transform.main")


def transform(
    online_sales: S3Input,
    iceberg_on_s3: S3Output,
    nxd_snowflake: Snowflake,
    ctx: ExecutionContext,
):
    """Transform sales data into velocity metrics.

    Parameter names match the input/output port names (hyphens become underscores).
    """
    trigger_ctx = ctx.triggered_by
    target_model = trigger_ctx.target_model if trigger_ctx else None

    # TODO: Read input data
    # df = read_from_s3(online_sales, "sales_transactions")

    # TODO: Transform
    # velocity_df = calculate_velocity(df)

    # TODO: Write output
    # save_to_s3(iceberg_on_s3, velocity_df, channel_sales_velocity.name)
    # save_to_snowflake(nxd_snowflake, velocity_df, channel_sales_velocity.name)

    _logger.info("Transform complete")
```

## contracts/completeness.py

```python
import pandas as pd
from nxd.data_product.contracts import VerifyResult


def verify(df: pd.DataFrame) -> VerifyResult:
    """Verify that null rate is below 10% for all columns."""
    null_rates = df.isnull().mean()
    max_null_rate = null_rates.max()

    if max_null_rate < 0.1:
        return VerifyResult("PASS", {"max_null_rate": float(max_null_rate)})
    else:
        worst_column = null_rates.idxmax()
        return VerifyResult(
            "FAILED",
            {"max_null_rate": float(max_null_rate), "worst_column": worst_column},
        )
```

## requirements.txt

```
nxd.core
nxd.data_product[spec]
pandas<=2.1.4
```
