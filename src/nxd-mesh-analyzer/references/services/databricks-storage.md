# Databricks storage inspection

- **Driver:** `nxd:databricks/storage:1.0.0` — category Storage, storage kind **db**
- **Plugin:** not yet built — implement `scripts/drivers/databricks_storage.py` from this recipe
- **Client:** `databricks-sql-connector`

## Attributes

`workspace_url`, `catalog`, `schema`, `sql_warehouse_id`, plus auth — `private_access_token`, or `principal_id`+`principal_secret`+`tenant_id` (OAuth M2M), or an `auth` JSON blob.

## Connection

- `server_hostname` — host from `workspace_url`.
- `http_path` — `/sql/1.0/warehouses/<sql_warehouse_id>`.
- `access_token` — `private_access_token` directly, or an OAuth token minted from the principal.

## Recipe

```sql
SHOW TABLES IN <catalog>.<schema>;
DESCRIBE TABLE EXTENDED <catalog>.<schema>.<table>;
SELECT table_name, last_altered FROM <catalog>.information_schema.tables
  WHERE table_schema = '<schema>';
```

`DESCRIBE TABLE EXTENDED` also reports format (delta/iceberg) and partition columns.
