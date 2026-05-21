# API inspection

- **Driver:** `nxd:api:0.1.0` — category API, storage kind **other**
- **Plugin:** not yet built — implement `scripts/drivers/api.py` from this recipe
- **Client:** any HTTP client (`requests`, `httpx`)

## Attributes

`url`, optional `username`, `token`.

## Recipe

APIs cannot be schema-introspected generically. Record the base URL as a **potential external input** with confidence **low**. If the user names a specific data endpoint, issue a single `GET` and infer the JSON response shape.

Never call mutating methods (`POST`, `PUT`, `PATCH`, `DELETE`).
