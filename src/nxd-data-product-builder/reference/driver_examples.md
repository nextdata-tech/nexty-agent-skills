# Driver Examples

## Contents
- PGVector
- API
- Azure Data Lake Storage (ADLS)
- ADLS with Databricks Spark

## PGVector

```python
from nxd.data_product.context import PgVector


def transform(
    ...
    pgvector: PgVector,
    ...
) -> None:
    ...

    table_name = (pgvector.model_tables or {}).get("<MODEL_NAME>", "<DEFAULT_NAME>")
    schema = pgvector.schema or "<DEFAULT_SCHEMA>"
    connection_string = (
        f"postgresql+psycopg://{pgvector.user}:{pgvector.password}"
        f"@{pgvector.host}:{pgvector.port}/{pgvector.database}"
    )

    _logger.info("Writing to %s.%s", schema, table_name)

    pg_engine = PGEngine.from_connection_string(url=connection_string)

    # pg_engine.init_vectorstore_table DDL
    # CREATE TABLE schema.table_name
    # (
    #     langchain_id uuid NOT NULL,
    #     content text COLLATE pg_catalog."default" NOT NULL,
    #     embedding vector(384) NOT NULL,
    #     langchain_metadata json,
    #     CONSTRAINT jira_embeddings_pkey PRIMARY KEY (langchain_id)
    # )
    # NOTE this will fail if the table already exists, there is no exists check
    pg_engine.init_vectorstore_table(
        vector_size=<VECTOR_SIZE>,  # Based on embedding model
        table_name=table_name,
        schema_name=schema,
    )
    store = PGVectorStore.create_sync(
        engine=pg_engine,
        embedding_service=embeddings,
        table_name=table_name,
        schema_name=schema,
    )
    store.add_documents(documents)

    _logger.info(
        "Transform complete — wrote %d chunks to %s.%s",
        len(documents),
        schema,
        table_name,
    )
```

## API

```python
from nxd.data_product.context import API

def _fetch_all_issues(api: API, project: Optional[str] = None) -> list[dict]:
    """Fetch all Jira issues via /rest/api/3/search/jql using nextPageToken pagination."""
    base_url = str(api.url).rstrip("/")
    auth = (str(api.username), str(api.token))
    ...

def transform(
    ...
    jira_api: API,
    ...
) -> None:
    _logger.info("Starting EXAMPLE transform")

    issues = _fetch_all_issues(jira_api, project=project)
    ...
```

## Azure Data Lake Storage - ADLS

```python
from nxd.data_product.context import AzureDataLakeStorage


def _get_adls_client(context: AzureDataLakeStorage) -> DataLakeServiceClient:
    credentials = ClientSecretCredential(
        context.tenant_id,
        context.client_id,
        context.client_secret,
    )
    return DataLakeServiceClient(f"https://{context.account_name}.dfs.core.windows.net", credential=credentials)


def parquet_to_adls(
    context: AzureDataLakeStorage,
    table: pa.Table,
    file_path: str,
) -> None:
    client = _get_adls_client(context)

    file_client = client.get_file_client(
        file_system=context.container,
        file_path=file_path,
    )

    buffer = BytesIO()
    pq.write_table(table, buffer)
    buffer.seek(0)

    file_client.upload_data(buffer, overwrite=True)


def transform(
    ...
    adls: AzureDataLakeStorage,
    ...
) -> None:
    _logger.info("Starting EXAMPLE transform")
    ...

    parquet_to_adls(adls, pyarrow_table, adls.model_paths[example_model.name].path)

    ...
```

## Azure Data Lake Storage - ADLS with Databricks Spark

```python
from nxd.data_product.context import AzureDataLakeStorage
from pyspark.sql import SparkSession


def spark_adls_configuration(context: AzureDataLakeStorage) -> dict[str, str]:
    return {
        # Disable account key authentication
        f"fs.azure.account.auth.type.{context.account_name}.dfs.core.windows.net": "OAuth",
        f"fs.azure.account.oauth.provider.type.{context.account_name}.dfs.core.windows.net": "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider",
        f"fs.azure.account.oauth2.client.id.{context.account_name}.dfs.core.windows.net": context.client_id,
        f"fs.azure.account.oauth2.client.secret.{context.account_name}.dfs.core.windows.net": context.client_secret,
        f"fs.azure.account.oauth2.client.endpoint.{context.account_name}.dfs.core.windows.net": f"https://login.microsoftonline.com/{context.tenant_id}/oauth2/token",
    }

def transform(
    ...
    spark: SparkSession,
    adls: AzureDataLakeStorage,
    ...
) -> None:
    _logger.info("Starting EXAMPLE transform")
    ...

    example_model_file_path = adls.model_paths["example-model"].path

    df = spark.read.format("delta").options(**spark_adls_configuration(adls)).load(
        f"abfss://{adls.container}@{adls.account_name}.dfs.core.windows.net/{example_model_file_path}",
    )
    ...
```
