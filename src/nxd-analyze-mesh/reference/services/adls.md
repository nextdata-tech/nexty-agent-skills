# ADLS (Azure Data Lake Storage) inspection

- **Driver:** `nxd:adls:2.0.0` — category Storage, storage kind **file**
- **Plugin:** `scripts/drivers/adls.py` ✓ implemented
- **Clients:** `azure-storage-blob`, `azure-identity` (lazy import)

## Attributes

`tenant_id`, `client_id`, `client_secret`, `account_name`.

## Recipe

```python
from azure.identity import ClientSecretCredential
from azure.storage.blob import BlobServiceClient
cred = ClientSecretCredential(tenant_id, client_id, client_secret)
svc = BlobServiceClient(f"https://{account_name}.blob.core.windows.net", cred)
```

List containers, then blobs per container. Group blobs by schema fingerprint and infer schema from a representative blob exactly as for S3 (see `s3.md` and the Schema-fingerprint grouping section of `../service-inspection.md`). Record blob count, bytes, and last-modified.

Storage kind is **file** — a source-aligned product reads ADLS and writes a database.
