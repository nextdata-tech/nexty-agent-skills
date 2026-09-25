# crm-pipeline

A governed, queryable view of the current CRM sales pipeline. Fetches deals
from the `api-source` REST API (`/deals`, paginated via a `next_cursor`
query-string cursor, continuing through every page including any page
reached only after a token refresh or a rate-limit retry). A deal is
current only when its source `status` is present and is neither the
literal value `deleted` nor the literal value `unknown` -- both are
excluded, never defaulted to current. Any other present status value is
treated as current; the source's complete set of active-status values
was not confirmed despite being asked twice, so this is a disclosed
assumption, not a source-confirmed enumeration (see `dp-blueprint.md`
Decisions > "Current-deal definition"). `deals` lands `deal_id`, `stage`,
`amount`, `updated_at`, plus `status` itself as
an internal-only verification column: it carries no semantic role, so it
never reaches `describe_models` or a governed query and is not part of
the stated Output, though it remains visible to direct access against the
physical table -- that's what makes it a genuine independent witness for
the `current-deals-non-deleted` promise below.

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

- `deals` (required, promised) -- one row per current deal: `deal_id`,
  `stage`, `amount`, `updated_at`, plus the internal-only `status`
  witness column. `amount` is `decimal(18, 6)` (models.py
  `AMOUNT_PRECISION` / `AMOUNT_SCALE`): the HTTP response is reparsed
  with `parse_float=Decimal` before dlt ever sees it, so a fractional
  amount survives as its exact source digits rather than a lossy binary
  float, and the transform raises rather than silently rounds if a
  source value ever needs more than 6 digits after the decimal point.
- `nxd_decisions` (required, promised) -- the ledger of this product's
  four rulings: the current-deal definition, the owner/email redaction,
  the decision not to compute an attention ranking, and the amount
  precision bound. The `current-deal-definition` row's `detail` field
  also carries this run's own fetched/excluded-deleted/
  excluded-missing-or-unknown/landed tally, captured while rows streamed
  through the ingestion filter.

## Output promises (`contracts/promises/`)

- `current-deals-non-deleted` -- queries the landed `status` witness
  column directly: `deleted`, `unknown`, `NULL`, and `''` must never
  appear on a landed row. Independent of the transform's own filter
  logic, since it reads the physical table rather than re-deriving the
  ingestion decision.
- `current-deals-no-owner-pii` -- both physical tables' own column
  catalogs (`PRAGMA table_info` on `deals` and `nxd_decisions`) contain
  no column naming owner or email, matching the promise's stated
  "every stored surface" scope.
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
