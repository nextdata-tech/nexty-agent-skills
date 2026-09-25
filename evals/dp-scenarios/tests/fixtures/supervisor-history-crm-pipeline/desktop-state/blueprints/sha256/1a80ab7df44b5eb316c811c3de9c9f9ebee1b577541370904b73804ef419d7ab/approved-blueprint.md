---
dp_spec_version: 3
name: crm_pipeline_current_v2
workflow: crm-pipeline-current-v2
status: proposed
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
source `status` field is present and is not the literal value `deleted`
or the literal value `unknown`. Exclude deleted deals, and exclude deals
whose `status` is missing, empty, or exactly `unknown`, from every
governed relation this product serves -- an absent status, and the
literal `unknown` value, are never treated as current by default. No
other status value was confirmed as a further exclusion despite being
asked twice, so any status value other than `deleted`, `unknown`, or
absent/empty is treated as current; this is a disclosed assumption, not
a source-confirmed enumeration of every active value. Retrieve every
deal across every page the source reports, continuing after a token
refresh or a rate-limit retry rather than stopping early.

Exclude owner name and owner email from every stored and served surface,
including any raw/internal landed relation, not only the final output.
These fields are dropped at ingestion rather than masked.

Do not compute, land, or expose a priority/attention ranking or score for
deals. No ranking threshold was supplied, so no ranking behavior is
in scope for this product.

## Terms

### Current deal

A deal whose source `status` field is present and is neither the literal
value `deleted` nor the literal value `unknown`. Three status outcomes
are distinguished: `deleted` (excluded, the tombstone), missing/empty or
exactly `unknown` (excluded, never treated as current by default), and
any other present value (current). The set of values a present, non-
`deleted`, non-`unknown` status can actually take was not confirmed by
the source despite being asked twice, so this term treats every such
value as current rather than requiring a positive enumeration; that gap
is disclosed here rather than silently assumed away. "Current" here is a
status classification, not a time-window calculation, so it needs no
clock anchor.

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
with a name and an email. The identifier, stage, amount, and last-updated timestamp are retained
when landing this input, plus the source status value itself: status is
landed as an internal-only column, used solely to verify the
current-row and deleted-row filtering independently of the transform's
own logic. It carries no semantic role and is absent from every governed
surface (`describe_models`, a governed query, and the product's stated
Output), reachable only by direct access to the physical relation. The
nested owner name and email are never landed in any stored surface of
this product, raw or output.

## Models

### Deals

Landed relation of current CRM deals. Grain: one row per deal. Fields:
deal_id, stage, amount, updated_at, plus the internal-only `status`
column. Owner name and owner email are not present in this model, or in
any other stored surface of this product, under any circumstance.
`status` is present only to verify current-row/deleted-row filtering; it
carries no semantic role, so it never reaches `describe_models` or a
governed query, and it is not part of the product's stated Output.

`amount` is landed using an exact decimal representation of the source
value: it preserves every digit the source reports, with no
floating-point truncation and no silent rounding to a coarser scale.

## Transform

### Filter to current deals

Filter operation: keep only rows whose `status` is present and is
neither the literal value `deleted` nor the literal value `unknown`;
discard rows whose `status` is the deleted tombstone, and discard rows
whose `status` is missing, empty, or exactly `unknown` -- an absent
status or the literal `unknown` value is excluded, never defaulted to
current. Any other present status value is treated as current.

### Project governed fields

Project operation: from the filtered rows, land deal_id, stage, amount,
updated_at, and the source `status` value as the columns of the `deals`
relation. `status` is landed for verification only: it carries no
semantic role, so it is absent from every governed surface even though
it is present in the physical relation. `amount` is
carried through as an exact decimal value end to end: the source
response is read so that its numeric digits are preserved exactly
(never round-tripped through binary floating point), and the transform
validates before landing that the value it is about to write reproduces
the source's own precision rather than a rounded approximation of it,
raising rather than silently rounding if a value ever needs more
precision than the landed column declares.

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

Use the source `status` field to distinguish current deals from deleted
deals: a deal is current only when `status` is present and is neither
the literal value `deleted` nor the literal value `unknown`. A deal
whose `status` is the deleted tombstone is excluded, and a deal whose
`status` is missing, empty, or exactly `unknown` is also excluded --
never defaulted to current. The operator was asked twice whether
`deleted`/`unknown`/absent are the complete set of non-current values,
or whether a specific positive "active" value should be matched instead,
and did not confirm either; this ruling proceeds on the disclosed
assumption that any other present status value is current, pending
correction. `status` itself is landed only as an internal-only column on
the `deals` relation, used solely to verify this filtering independently
of the transform's own logic; it carries no semantic role, so it never
reaches `describe_models`, a governed query, or the product's stated
Output, and a consumer using the governed surface never sees it. It
remains visible to direct access against the physical relation, which is
what makes it useful as a verification witness.

### Owner and email redaction

Owner name and owner email are dropped at ingestion and never land in
any stored surface of this product, raw or served, per the operator's
explicit instruction to keep owner and email details redacted.

### No attention ranking

This product does not compute, land, or expose a priority or attention
ranking of deals, because no ranking threshold was supplied. This is a
scope exclusion, not a deferred feature, per the operator's explicit
instruction.

### Amount precision

Land `amount` as an exact decimal value, sized to 18 total digits with 6
digits after the decimal point, per the operator's explicit instruction
that amount must preserve the source value without floating-point
truncation or silent rounding. This bound was not stated by the source;
it is the agent's chosen ceiling, generous enough for ordinary currency
values including sub-cent precision. The transform validates every
landed value reproduces the source's own digits exactly within that
bound and raises rather than silently rounding if a source value ever
needs more than 6 digits after the decimal point.

## Open Questions
