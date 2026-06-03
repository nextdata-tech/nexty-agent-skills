"""Shim re-exporting the nxd symbols `spec.py` uses via `from nxd_spec import *`.

Pulls in the project's own `amazon_sales` model and `transform` function
so they're available at spec-evaluation time, then re-exports the
spec-builder names through `__all__`.
"""

from models import amazon_sales
from nxd.spec import (
    SupportedFormat,
    code,
    data_product,
    data_product_access,
    data_product_output,
    owner,
    s3_config,
    snowflake_config,
    source_aligned_input,
    storage,
)
from nxd.spec.conditions import scheduled
from transform import transform

__all__ = [
    "SupportedFormat",
    "amazon_sales",
    "code",
    "data_product",
    "data_product_access",
    "data_product_output",
    "owner",
    "s3_config",
    "scheduled",
    "snowflake_config",
    "source_aligned_input",
    "storage",
    "transform",
]
