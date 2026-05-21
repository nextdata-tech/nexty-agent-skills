# Pinecone inspection

- **Driver:** `nxd:pinecone:0.1.0` — category Storage, storage kind **other** (vector)
- **Plugin:** not yet built — implement `scripts/drivers/pinecone.py` from this recipe
- **Client:** `pinecone`

## Attributes

`pinecone_secret_api_key`, `index`, `region_name`.

## Recipe

Call `index.describe_index_stats()` for vector dimension, total vector count, and namespaces. Sample one query to collect metadata keys. Record the index as an `index`-kind asset.
