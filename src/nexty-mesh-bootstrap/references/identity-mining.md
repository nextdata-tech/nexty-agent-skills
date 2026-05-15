# Identity & Role Mining

Phase 4 of the wizard. Goal: produce `identity-map.md` and an `identities` array in `mesh-inventory.json`. Identities ground product ownership, stewardship, and consumer-access decisions; role groupings often validate or correct domain boundaries from Phase 2.

This phase mirrors the workflow of vendor identity-migration tools — IdP exports get classified into clusters of users who share groups and app-access patterns, then those clusters become candidate roles attached to data products.

## Intake order

1. Ask: "Do you have an IdP export — Okta CSV, Entra ID `Get-MgUser` / `Get-MgGroup` output, AD group dump, SailPoint role definitions, or an HR roster?"
2. File ingest → role-mining heuristic → reconcile against domains.
3. Or Q&A → placeholder identity records → `TODO(identity)` rows for missing exports.

## Supported IdP exports

| Source | Typical format | What to extract |
|---|---|---|
| Okta | CSV with `Login, FirstName, LastName, Email, GroupMemberships, AssignedApps` | identity rows + group memberships + app assignments |
| Entra ID (Azure AD) | JSON from `Get-MgUser`, `Get-MgGroup`, `Get-MgGroupMember` | same as Okta |
| Active Directory | LDAP dump or `Get-ADUser` CSV | identity + group memberships |
| SailPoint IdentityIQ | Role definition export (XML or JSON) | role names + entitlements + member identities |
| HR roster | CSV with `email, manager, dept, title` | identity rows + organizational hierarchy (no app data) |

If the user has multiple, ingest all and merge by primary identifier (lowercased email).

## Role-mining heuristic

After identities + groups + app assignments are loaded, cluster groups into candidate roles:

1. For each group `g`, build a feature vector: `{members: set, apps: set, name_tokens: set}`.
2. Compute pairwise overlap: `Jaccard(members(g_i), members(g_j))`.
3. Merge `g_i` and `g_j` into the same role-cluster when `Jaccard >= 0.7` AND `app_overlap >= 0.5`.
4. Name each cluster from the longest common token in `name_tokens` (e.g. groups `dap-research-prod-readers`, `dap-research-stage-readers`, `dap-research-readers` → role `dap-research-readers`).

This is intentionally simple — surface it to the user as a *proposal*, never as fact. The user must confirm or edit each cluster.

## Domain-boundary reconciliation

After role clusters are proposed, walk through each and check the name tokens against the domain tree from Phase 2:

- Token matches a known domain (`research`, `commercial`, `ddq`) → propose linking the role to that domain.
- Token names a domain not in Phase 2 (`bioinformatics`, `medaffairs`) → flag as **possible domain miss**: surface to user and ask whether to add a domain in Phase 2 or treat as a subdomain alias.
- No domain token in the role name → propose `domain: shared` and ask the user to confirm.

Record reconciliation outcomes in `identity-map.md` so the user can re-open Phase 2 if the identity data revealed missing domains.

## Q&A path

When no IdP export is available, collect minimal placeholders per domain:

1. "Who is the producer team / engineering team for `<domain>`?"
2. "Who is the data steward for `<domain>`?"
3. "Top 1–3 consumer teams for `<domain>` data?"
4. "Any compliance reviewer / approver?"

Each answer becomes a placeholder identity record with `confidence: low` and a TODO to confirm against the IdP later.

## Identity record structure

```json
{
  "id": "identity:user@argenx.com",
  "kind": "user|group|service-principal|role",
  "primary_id": "user@argenx.com",
  "display_name": "Jane Doe",
  "groups": ["dap-research-prod-readers", "okta-everyone"],
  "apps": ["Snowflake-Prod", "Databricks-Research"],
  "domain_links": [{"domain": "Research", "role": "producer", "confidence": "medium"}],
  "evidence": ["evidence:okta-export-2026-04-01"],
  "confidence": "high"
}
```

Role-cluster records:

```json
{
  "id": "role:dap-research-readers",
  "kind": "role",
  "members": ["identity:user@argenx.com", "..."],
  "apps": ["Snowflake-Prod"],
  "proposed_domain": "Research",
  "proposed_function": "consumer",
  "evidence": ["evidence:okta-group-dap-research-prod-readers"],
  "confidence": "medium",
  "review_status": "pending"
}
```

## identity-map.md template

```markdown
# Identity Map

> Source: <file path(s) or "Q&A 2026-05-06">

## Roles (clustered)

| role | proposed domain | function | members | apps | confidence | status |
|------|-----------------|----------|---------|------|------------|--------|
| dap-research-readers | Research | consumer | 14 | Snowflake-Prod | medium | pending |
| ...  |

## Domain reconciliation

- Role `medaffairs-stewards` references a domain not yet in the domain tree. Suggest adding `Medical Affairs` as a Commercial subdomain. Confirm in Phase 2.
- Role `corp-it-admins` has no domain token — proposed `shared`.

## Open questions

- Pulled from `open-todos.md`, filtered by `phase: identity`.
```

## Privacy

- Treat identity records as sensitive. They live in `.context/` (gitignored).
- Never include passwords, secrets, or auth tokens. Strip those fields on ingest.
- The identity map is for *modeling*, not for any access-control change. The skill never grants or revokes anything.

## Boundary checks before exiting Phase 4

- Every role cluster has a proposed domain (or explicit `shared`).
- Every flagged "possible domain miss" has a resolution: added to Phase 2, treated as alias, or deferred via TODO.
- The user has explicitly confirmed the role list (or logged a deferral).
