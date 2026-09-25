---
dp_spec_version: 3
name: crm_pipeline
workflow: crm-pipeline
status: approved
approved_content_hash: sha256:46a3a974100e90ba38d33b2d0f12c8c3ff691bc8c4e085ec7e846f204882aa0b
approved_proposal_hash: sha256:f65a88c37f52e8a58fa68927d27972b18dc4e1f3cea9b2bef3919b47c727873a
---

## Intent

Provide a governed, queryable view of the current CRM sales pipeline for
sales-ops and revenue-analyst review. The product exposes active deal
records (identifier, stage, amount, last-updated time) while keeping
account-owner identity details out of every stored and served surface.

## Questions

What deals are currently active in the CRM pipeline, and what stage,
amount, and last-updated time does each have?

What is the count and total amount of active deals, broken down by stage?

## Scope

Include only current deals from the CRM deals source: records whose
source `status` field marks them active rather than deleted. Exclude
deleted deals entirely from every relation this product lands or serves.
Retrieve every deal across every page the source reports, continuing
after a token refresh or a rate-limit retry rather than stopping early.

Exclude owner name and owner email from every stored and served surface,
including any raw/internal landed relation, not only the final output.
These fields are dropped at ingestion rather than masked.

Do not compute, land, or expose a priority/attention ranking or score for
deals. No ranking threshold was supplied, so no ranking behavior is
in scope for this product.

## Terms

### Current deal

A deal whose source `status` field indicates it is active rather than
deleted, evaluated against the value the source reports for that record.
"Current" here is a status classification, not a time-window calculation,
so it needs no clock anchor.

### Redacted field

A field that is removed from all landed and served relations of this
product, rather than masked, truncated, or replaced with placeholder
text. Owner name and owner email are the redacted fields for this
product.

## Inputs

### Deals

Load deal records from the CRM deals API source (the `api-source`
service's `/deals` endpoint), continuing through every page of its
cursor-based pagination until no further page remains, including any
page reached only after a token refresh or a rate-limit retry. Each
source record carries an identifier, a deal name, a stage (one of
prospecting, qualification, negotiation, closed_won, or closed_lost), an
amount, a status, a last-updated timestamp, and a nested owner object
with a name and an email. Only the identifier, stage, amount, and
last-updated timestamp are retained when landing this input. The source
status value is read only in memory to decide whether a record is
current and is never landed in any stored surface of this product. The
nested owner name and email are likewise never landed in any stored
surface of this product, raw or output.

## Models

### Deals

Landed relation of current CRM deals. Grain: one row per deal. Fields:
deal_id, stage, amount, updated_at. Owner name, owner email, and the
source status field are not present in this model, or in any other
stored surface of this product: status is consulted only in memory
during ingestion to decide which rows are current, and is discarded
before any row is landed.

## Transform

### Filter to current deals

Filter operation: in memory, before any row is landed, keep only rows
whose `status` marks the deal as active (current); discard rows whose
`status` marks the deal as deleted, and discard the `status` value
itself once this decision is made for a kept row -- it is never landed.

### Project governed fields

Project operation: from the filtered, in-memory rows, land deal_id,
stage, amount, and updated_at as the only columns of the `deals`
relation. No other field, including `status`, is landed.

No scoring, weighting, or ranking step is included anywhere in this
transform: the product does not compute a priority or attention rank for
deals, because no ranking threshold was supplied.

## Outputs

### Current deals

The governed, redacted list of currently active CRM pipeline deals: one
row per active deal with deal_id, stage, amount, and updated_at.

#### Promises

Every row in this output is a current (non-deleted) deal; deleted deals
never appear. No row in this output, and no other stored surface of this
product (including any raw/internal landed relation), includes owner
name or owner email. No row or field in this output represents a
priority or attention ranking.

## Decisions

### Current-deal definition

Use the source `status` field to distinguish current (active) deals from
deleted deals; "current" means the source reports the deal as active,
not deleted. The status value itself is never landed in any stored
surface of this product, including the `deals` relation: it is read and
consulted only in memory during ingestion, so a consumer with direct
access to the landed data sees no `status` column anywhere.

### Owner and email redaction

Owner name and owner email are dropped at ingestion and never land in
any stored surface of this product, raw or served, per the operator's
explicit instruction to keep owner and email details redacted.

### No attention ranking

This product does not compute, land, or expose a priority or attention
ranking of deals, because no ranking threshold was supplied. This is a
scope exclusion, not a deferred feature, per the operator's explicit
instruction.

## Open Questions
