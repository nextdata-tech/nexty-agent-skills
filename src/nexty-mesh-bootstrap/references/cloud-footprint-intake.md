# Cloud Footprint & Accounts Intake

Phase 3 of the wizard. Goal: produce `cloud-footprint.md` and a `cloud_footprint` array in `mesh-inventory.json`. The matrix this phase produces is the **primary input** for proposing infra profiles in Phase 7.

## Intake order

1. Ask: "Do you have an Enterprise Architecture or Data Platform Assessment doc that lists clouds, platforms, and account counts?"
2. File ingest, Q&A, or hybrid — same fallback ladder as Phase 2.

## What to extract per platform

For every distinct platform the org uses, capture:

| Field | Notes |
|---|---|
| `platform` | Snowflake, Databricks, Fabric, BigQuery, Redshift, S3, ADLS, GCS, Postgres, Kafka, etc. |
| `clouds` | AWS / Azure / GCP / on-prem. Allow multiple. |
| `regions` | Per cloud — e.g. `us-east-1`, `eu-central-1`, `Frankfurt`. |
| `account_count` | Integer. Be exact when the user knows it. |
| `env_split` | `["dev", "test", "prod"]` or `["non-prod", "prod"]` etc. |
| `owner_domain` | Maps to a domain from Phase 2 when known. |
| `purpose` | One sentence. e.g. "DDQ analytical backbone", "Commercial reporting". |
| `notes` | Multi-cloud caveats, GxP/non-GxP split, sharing patterns. |

## Example: argenx DAP assessment

Source: `EA-argenx-DAP-Assessment.md`. Extracted matrix:

| platform | clouds | regions | accounts | env_split | owner_domain | notes |
|---|---|---|---|---|---|---|
| Snowflake | AWS, Azure | AWS (Commercial), Frankfurt (DDQ) | 8 | Dev/Test/Prod (DDQ) + Prod/Non-prod (Commercial) | shared | Hybrid; Veeva Vault ingest via S3; LSAF on Azure. |
| Databricks | Azure | (one region) | 1 workspace today | Non-prod only | Discovery / Research | Early adoption; not a Snowflake replacement. |
| Fabric | Azure | — | — | — | shared | Used selectively for Power BI. |
| ADLS | Azure | Frankfurt | — | — | DDQ | LSAF storage. |
| S3 | AWS | (multi) | — | — | Commercial | Veeva Vault landing. |

This matrix is the kind of fidelity to aim for. If a row is incomplete, mark `?` and add a TODO.

## Q&A path

For each platform the user names, ask in order:

1. "Which clouds does it run on?"
2. "Which regions?"
3. "How many accounts/workspaces total?"
4. "What's the environment split — dev/test/prod, prod/non-prod, or other?"
5. "Which domain owns it, or is it shared?"

Stop after the user has covered every platform they remember. Ask: "Anything else? If not sure, we can add a TODO and revisit." Common platforms to prompt by name if the user trails off: Snowflake, Databricks, BigQuery, Redshift, Fabric, S3, ADLS, GCS, Postgres, Kafka, MongoDB, Elastic.

## Partial knowledge

Append to `open-todos.md`:

```markdown
- [ ] phase: cloud-footprint | item: Azure DevOps repo list | blocker: not handy | added: 2026-05-06
- [ ] phase: cloud-footprint | item: Snowflake account count for Commercial | blocker: confirm with platform team | added: 2026-05-06
```

## Proposing infra profiles

After the matrix is filled, propose **one infra profile per `(domain, primary cloud)` pair**, plus shared profiles for cross-domain platforms.

Heuristic:

1. For each domain in `domains`, find platforms whose `owner_domain` matches.
2. Group those platforms by primary cloud.
3. Each group → one profile candidate. Name format: `<domain>-<cloud>` (e.g. `commercial-aws`, `ddq-azure`).
4. For platforms with `owner_domain: shared`, add to `shared-<cloud>` profile.
5. If a domain has only one cloud, drop the cloud suffix: `research-dbx`, `commercial-sf`.

Surface the list to the user before persisting:

```
Proposed infra profiles (5):
  1. commercial-aws        — Snowflake (Commercial Prod/Non-prod), S3 (Veeva)
  2. ddq-azure             — Snowflake (DDQ Frankfurt), ADLS (LSAF)
  3. research-dbx-azure    — Databricks (research workspace)
  4. shared-azure          — Fabric, Azure-hosted shared services
  5. shared-aws            — cross-domain S3
```

Confirm or edit. Record the final list in `mesh-inventory.json#/infra_profiles`.

## cloud_footprint record structure

```json
{
  "platform": "Snowflake",
  "clouds": ["AWS", "Azure"],
  "regions": ["AWS:us-east-1", "Azure:Frankfurt"],
  "account_count": 8,
  "env_split": ["dev", "test", "prod", "prod-commercial", "non-prod-commercial"],
  "owner_domain": "shared",
  "purpose": "Enterprise analytical backbone",
  "evidence": ["evidence:dap-assessment-section-1.2.2"],
  "confidence": "high",
  "notes": "Hybrid AWS+Azure; eight accounts split DDQ Dev/Test/Prod and Commercial Prod/Non-prod."
}
```

## Boundary checks before exiting Phase 3

- Every platform the user named in Phase 5's collect-inputs preview also appears here.
- Every `owner_domain` value is either `shared` or matches a domain from Phase 2.
- Account counts are integers or `null` with a TODO.
- The proposed infra-profile list is confirmed (or deferred via TODO).
