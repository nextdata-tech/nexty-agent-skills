# Driver Examples

## PGVector

Usage within `spec.py`

```
from nxd.spec import (
    pg_vector_config,
)

...
.port(
    "<PORT_NAME>",
    storage(
        "https://app.westpac.nextopia.dev/infra-profile/<INFRA_PROFILE_NAME>#/services/<SERVICE_NAME>"
    ).config(
        pg_vector_config(schema="<SCHEMA_NAME_IF_PRESENT>")
        # OPTIONAL Manually map models to custom table names
        .target_table("<PG_TABLE_NAME>", <NXD_MODEL_OBJ>)
    )
)
```

Usage within `transform.py`

```
from nxd.data_product.context import PgVector


def transform(
    ... 
    <PORT_NAME>: PgVector,
    ...
):
    ....
    connection_string = (
        f"postgresql+psycopg2://{pgvector.user}:{pgvector.password}"
        f"@{pgvector.host}:{pgvector.port}/{pgvector.database}"
    )
    ...
    qualified_table_name = f"{pgvector.schema}.{pgvector.models['<MODEL_NAME>'].name}"
```

### Azure Data Lake Storage (ADLS)

Example usage within `spec.py`

```
from nxd.spec import (
    adls_config,
)

...
.port(
    "<PORT_NME>",
    storage(
        "https://app.westpac.nextopia.dev/infra-profile/<INFRA_PROFILE_NAME>#/services/<SERVICE_NAME>"
    )
    .config(
        adls_config(file_type=SupportedFormat.PARQUET)
        # OPTIONAL Manually map models to custom locations
        .target_file("<FILE_NAME>.parquet", <NXD_MODEL_OBJ>)
    )
)
```

Example usage within `transform.py`

```
from azure.identity import ClientSecretCredential
from azure.storage.filedatalake import DataLakeServiceClient
from nxd.data_product.context import AzureDataLakeStorage


def transform(
    ... 
    <PORT_NAME>: AzureDataLakeStorage,
    ...
):
    ...
    credential = ClientSecretCredential(
        tenant_id=<PORT_NAME>.tenant_id,
        client_id=<PORT_NAME>.client_id,
        client_secret=<PORT_NAME>.client_secret,
    )
    adls_client = DataLakeServiceClient(
        account_url=f"https://{<PORT_NAME>.account_name}.dfs.core.windows.net",
        credential=credential,
    )
```