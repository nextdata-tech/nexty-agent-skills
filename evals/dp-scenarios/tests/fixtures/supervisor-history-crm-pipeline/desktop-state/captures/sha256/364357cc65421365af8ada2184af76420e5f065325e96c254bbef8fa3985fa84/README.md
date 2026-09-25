# crm-pipeline

A governed, queryable view of the current CRM sales pipeline. Fetches deals
from the `api-source` REST API (`/deals`, paginated via a `next_cursor`
query-string cursor, continuing through every page including any page
reached only after a token refresh or a rate-limit retry), keeps only rows
whose source `status` is not `deleted`, and lands exactly `deal_id`,
`stage`, `amount`, and `updated_at` as the only columns of the `deals`
table -- there is no physical surface, governed or raw, where the source
`status` value appears. It is read only in memory during ingestion to
decide which rows are current, then discarded.

Owner name and owner email are read from the source response only inside
the transform's row flattener and are never copied into the row this
closure lands -- they are absent from every physical and served surface,
not merely hidden by a role or a promise. This product does not compute,
land, or expose any priority/attention ranking, because no ranking
threshold was supplied when it was approved.

## Reopening this closure

```
resume_data_product(workflow="crm-pipeline")
```

## Models

- `deals` (required, promised) -- one row per current deal: exactly
  `deal_id`, `stage`, `amount`, `updated_at`. No other column.
- `nxd_decisions` (required, promised) -- the ledger of this product's
  three rulings: the current-deal definition, the owner/email redaction,
  and the decision not to compute an attention ranking. The
  `current-deal-definition` row's `detail` field also carries this run's
  own fetched/excluded-deleted/landed tally, captured while rows streamed
  through the ingestion filter, before the source `status` value was
  discarded.

## Output promises (`contracts/promises/`)

- `current-deals-non-deleted` -- recomputes `deals`' row count directly
  from the physical table and reconciles it against the fetched/excluded
  tally recorded in the `nxd_decisions` ledger for this run. Status is
  never landed anywhere (per the approved blueprint), so this
  reconciliation is the independent witness rather than a landed status
  column.
- `current-deals-no-owner-pii` -- the `deals` table's own column catalog
  (`PRAGMA table_info`) contains no column naming owner or email.
- `current-deals-no-ranking` -- the `deals` table's own column catalog
  contains no priority/rank/attention/score column.

## Credentials

The `api-source` service in `infra-profile.yaml` carries only non-secret
topology: `base_url`, `auth_header`, `auth_scheme`, `auth_refresh_path`,
and the `endpoint_deals*` attributes. It carries **no live token value**.
Instead, `credential_env` names the environment variable
(`NXD_EVAL_SOURCE_TOKEN`) the transform reads at run time
(`os.environ[secrets["credential_env"]]`) to obtain the live bearer token;
that variable must be set in the environment the transform runs in. On a
401 the transform refreshes the token once via `auth_refresh_path` and
replays the request; on a 429 it waits once for the capped `Retry-After`
delay and replays. See `SENSITIVE` for the file/attribute this rule
covers.

## Staging placeholder note

This closure needs no CSV connector -- `deals` is fetched over HTTP and
`nxd_decisions` is landed reference data this closure authors itself. The
`csv-source-path` file and `data/` tree exist only to satisfy the desktop
supervisor's staging preflight for every closure (see
`reference/api-source.md` in the generator skill); `data/nxd_decisions/`
is real landed data, not a placeholder.
