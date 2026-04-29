# Driver Examples

## PGVector

```
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
    # CREATE TABLE IF NOT EXISTS schema.table_name
    # (
    #     langchain_id uuid NOT NULL,
    #     content text COLLATE pg_catalog."default" NOT NULL,
    #     embedding vector(384) NOT NULL,
    #     langchain_metadata json,
    #     CONSTRAINT jira_embeddings_pkey PRIMARY KEY (langchain_id)
    # )
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

```
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
```
