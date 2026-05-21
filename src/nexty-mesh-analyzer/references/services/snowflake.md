# Snowflake inspection

- **Driver:** `nxd:snowflake:1.0.0` — category Storage, storage kind **db**
- **Plugin:** `scripts/drivers/snowflake.py` ✓ implemented
- **Client:** `snowflake-connector-python` (lazy import)

## Attributes

`account`, `role`, `warehouse`, `database`, and **one** auth credential — `user`+`pass`, `user`+`private_key_pem`, or `user`+`pat`.

## Auth

- Password — `connect(..., password=pass)`.
- Key-pair — load `private_key_pem` with `cryptography`, pass DER bytes as `private_key=`.
- PAT — `connect(..., password=pat, authenticator="programmatic_access_token")`.

## Recipe

Read-only SQL:

```sql
SHOW SCHEMAS IN DATABASE <database>;
SHOW TABLES IN DATABASE <database>;
DESCRIBE TABLE <database>.<schema>.<table>;
SELECT table_schema, table_name, row_count, bytes, last_altered
  FROM <database>.INFORMATION_SCHEMA.TABLES;
SELECT * FROM <database>.<schema>.<table> LIMIT 100;   -- only if schema unclear
```

Use `INFORMATION_SCHEMA.TABLES` for `row_count` / `last_altered` instead of scanning, and `INFORMATION_SCHEMA.COLUMNS` for schemas.

## Per-source-type rule

Tables named `<table>_CLONE_<digits>` are platform clones, not real outputs — the plugin's `excluded_asset` drops them. See `../connection-matching.md`.
