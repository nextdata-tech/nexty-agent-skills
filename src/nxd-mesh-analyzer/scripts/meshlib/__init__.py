"""meshlib — generic, service-type-agnostic core for nxd-mesh-analyzer.

No module here imports a service SDK (boto3, snowflake, ...). Service-specific
behaviour lives in the `drivers/` package and is injected at runtime via a
Registry (see meshlib.registry).
"""
