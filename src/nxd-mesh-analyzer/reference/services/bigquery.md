# BigQuery inspection

- **Driver:** `nxd:gcp/bigquery:1.0.0` — category Storage, storage kind **db**
- **Plugin:** not yet built — implement `scripts/drivers/bigquery.py` from this recipe
- **Client:** `google-cloud-bigquery`

## Attributes

`access_token` (base64-encoded service-account JSON), `project_id`, `dataset_id`.

## Recipe

```python
import base64, json
from google.oauth2 import service_account
info = json.loads(base64.b64decode(access_token))
creds = service_account.Credentials.from_service_account_info(info)
```

List tables in `project_id.dataset_id`. For each, read `table.schema` (fields + types), `table.num_rows`, `table.num_bytes`, `table.modified`, and `table.time_partitioning` if present (a scheduling hint).
