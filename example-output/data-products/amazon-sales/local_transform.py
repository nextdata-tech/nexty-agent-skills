"""Run the amazon-sales transform locally against real services.

Loads service credentials from environment variables (or a `.env` file
beside this script — see `.env.example`) and synthesises the runtime
context objects so `transform()` can be invoked exactly as the platform
would invoke it.
"""

from __future__ import annotations

import logging
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:
    pass

from nxd.core.context import SecretString
from nxd.data_product.context import S3Input, Snowflake

from transform import transform

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(f"Required environment variable '{name}' is not set")
    return value


if __name__ == "__main__":
    # boto3 picks credentials up from the environment / AWS profile automatically;
    # no need to wire them into the S3Input context.
    s3_source = S3Input(
        bucket=_require("S3_BUCKET"),
        model_output_paths={
            "amazon_sales": os.environ.get(
                "S3_KEY", "check-state/demo/amazon-sales.csv"
            )
        },
        models={},
        model_urls={},
    )

    snowflake = Snowflake(
        url=os.environ.get("SNOWFLAKE_URL", ""),
        account=_require("SNOWFLAKE_ACCOUNT"),
        user=_require("SNOWFLAKE_USER"),
        secret_password=SecretString(_require("SNOWFLAKE_PASSWORD")),
        secret_private_key_pem=None,
        secret_pat=None,
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "daff_db"),
        schema=os.environ.get("SNOWFLAKE_SCHEMA", "CHECK_POSTFIX_STAGING"),
        role=os.environ.get("SNOWFLAKE_ROLE"),
        model_tables={"amazon_sales": "AMAZON_SALES"},
        models={},
    )

    transform(s3_source, snowflake)
