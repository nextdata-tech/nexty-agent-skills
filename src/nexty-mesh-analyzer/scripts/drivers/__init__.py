"""Service-type driver plugins.

Each module here owns one service type and the SDK imports it needs (boto3,
snowflake, ...). `meshlib` never imports this package — an entrypoint builds
the registry from `ALL` and injects it into the common code.

To add a service type: create `drivers/<name>.py` exposing a `DRIVER`
(see meshlib.registry.Driver), then add it to `ALL`.
"""
from meshlib.registry import Registry

from . import s3, snowflake, adls

ALL = [s3.DRIVER, snowflake.DRIVER, adls.DRIVER]


def default_registry():
    """Registry of every built-in driver plugin."""
    return Registry(ALL)
