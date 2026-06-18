# Postgres / pgvector inspection

- **Drivers:** `nxd:postgres:*`, `nxd:pgvector:1.0.0` — category Storage, storage kind **db**
- **Plugin:** not yet built — implement `scripts/drivers/postgres.py` from this recipe
- **Client:** `psycopg2` (`psycopg2-binary`)

## Attributes

`host`, `port`, `database`, `user`, `password`.

## Recipe

```sql
SELECT table_schema, table_name FROM information_schema.tables
  WHERE table_schema NOT IN ('pg_catalog','information_schema');
SELECT column_name, data_type FROM information_schema.columns
  WHERE table_schema = %s AND table_name = %s;
SELECT reltuples::bigint AS est_rows FROM pg_class WHERE relname = %s;
```

For `pgvector`, columns of type `vector` are embedding columns — record their dimension.

`redshift` inspects the same way (also `psycopg2` + `information_schema`).
