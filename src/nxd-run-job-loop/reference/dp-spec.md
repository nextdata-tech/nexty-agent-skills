# `dp-spec.md` — the editable plan between intent and generated data product

## Contents

- [Authoring contract](#authoring-contract)
- [Frontmatter](#frontmatter)
- [Sections](#sections)
- [Transform vocabulary](#transform-vocabulary)
- [Claude Desktop form contract](#claude-desktop-form-contract)
- [Worked v2 example](#worked-v2-example)

`dp-spec.md` is the user-owned intermediate representation for the local data
product loop. It is ordinary Markdown with a deliberately tiny frontmatter
block. A user can edit the prose, lists, and labelled fields directly; the
validator reports exact stable paths instead of silently repairing meaning.

## Authoring contract

- Claude Desktop pre-fills this document from the user's request and source
  material. The user reviews and edits it; an empty form is not the normal path.
- Required information that cannot be inferred becomes an entry in **Open
  Questions**, not a blank field or an invented default.
- `status: approved` is a separate user decision. A semantic patch to an
  approved document atomically changes it to `proposed` and clears its approval
  binding. Approval binds the semantic content hash, excluding lifecycle fields.
- The parser preserves untouched bytes, comments, Unicode, and LF line endings
  for supported targeted patches. It rejects CRLF rather than normalizing it.
  Stable paths support scalar/prose replacement; entity/list structure changes
  are reviewed proposal edits and are not silently applied. Targeted scalar and
  prose patches currently accept one-line values only; a multiline change is a
  reviewed proposal/emit operation so the form cannot accidentally change the
  Markdown structure.
- The active contract is version 2. Older version values fail with
  `unsupported_version`; no migration or fallback parser exists.

## Frontmatter

```yaml
---
dp_spec_version: 2
name: monthly_revenue
workflow: monthly-revenue
status: proposed
---
```

Only these lifecycle fields are allowed, plus `approved_content_hash` on an
approved document. The content hash includes the name, workflow, and complete
body semantics, but excludes `status` and `approved_content_hash`.

## Sections

The document has exactly these headings. Body content is Markdown, not a YAML
payload:

1. **Intent** — the outcome and audience.
2. **Questions** — stable question IDs and the natural-language questions that
   outputs must answer.
3. **Scope** — inclusions, exclusions, grain boundaries, and assumptions.
4. **Inputs** — source bindings, type, location, and description.
5. **Models** — named relations and their fields, each with exactly one origin:
   base/reference from an input, derived from one transform step, or a typed
   view expression.
6. **Transform** — an acyclic graph of named steps. Each step writes exactly
   one declared derived model.
7. **Outputs** — the user-visible products. Each output names one model,
   non-empty question references, a projection, ordering, and delivery refs.
8. **Delivery** — runtime channel, target, and delivery semantics.
9. **Contracts** (optional) — typed executable guarantees attached to an Input
   or Output; their approved inventory is locked with the spec hash.
10. **Decisions** — provenance and rationale only; it is not executable policy.
11. **Open Questions** — unresolved questions, their target, and whether they
    block approval/materialization.

Every question must reach an output, and every delivery must be used by an
output. A standalone `Policy` heading is invalid. Decision procedures belong
to a Transform step or a reference Model and are represented by a versioned
`id@version` procedure reference.

## Transform vocabulary

The first release uses only these closed operations:

`filter`, `project`, `derive`, `join`, `aggregate`, `union`, `deduplicate`, and
`apply_procedure`. An `apply_procedure` step has one data input; its versioned
`Procedure` is metadata for the operation, not a second item in `Inputs`. A
reference Model may carry the same procedure reference when it is the named
owner of that decision logic.

The operation-specific fields are typed and validated. Field references in a
transform are qualified as `model.field`. Joins declare type, cardinality,
join keys, and unmatched-row behavior. Aggregates declare grouping and null
handling. Unions declare alignment and missing-field behavior. Deduplication
declares keys, ordering, and the winner rule. Join null-key behavior is
explicit. A procedure step also declares its output `Fields`; its result shape
is not inferred from an opaque procedure body. Derived expressions are a small
closed vocabulary of field copy and named scalar functions; arbitrary SQL or
free-form expressions are rejected.

## Claude Desktop form contract

The harness should render the parser's source-map paths as controls and group
them in the same section order. It should show a prefilled read-back first,
highlight validation findings inline, keep unknown/unresolved material visible,
and offer explicit **Propose patch**, **Approve**, and **Reject** actions.
Approval is disabled while validation has errors or a blocking Open Question.
The harness must never overwrite the user's whole file from a canonical emit;
it uses a stale-hash-checked targeted patch or presents a reviewed proposal.

## Worked v2 example

```markdown
---
dp_spec_version: 2
name: monthly_revenue
workflow: monthly-revenue
status: proposed
---

## Intent

Provide an auditable monthly revenue relation for finance review.

## Questions

### Question `monthly_revenue_by_customer`

What was monthly revenue for each customer?

## Scope

Includes paid orders only and excludes refunds until a separately declared model adds them.

## Inputs

### Input `orders_csv`
- Type: `csv`
- Location: `data/orders.csv`
- Description: Order rows supplied by finance.

## Models

### Model `orders`
- Kind: `base`
- Input: `orders_csv`
- Description: Pristine order relation.
- Grain: one row per order
- Key: `order_id`
- Fields: `order_id, customer_id, month, amount_usd`

### Model `monthly_customer_revenue`
- Kind: `derived`
- Description: Monthly revenue per customer.
- Grain: one row per customer and month
- Key: `customer_id, month`
- Fields: `customer_id, month, revenue`
- Produced by: `aggregate_monthly_revenue`

## Transform

### Step `aggregate_monthly_revenue`
- Operation: `aggregate`
- Inputs: `orders`
- Output: `monthly_customer_revenue`
- Group by: `orders.customer_id, orders.month`
- Measures: `revenue=sum(orders.amount_usd)`
- Null handling: `ignore`

## Outputs

### Output `monthly_revenue_port`
- Model: `monthly_customer_revenue`
- Questions: `monthly_revenue_by_customer`
- Projection: `customer_id, month, revenue`
- Order by: `month desc, customer_id asc`
- Delivery refs: `finance_semantic_port`

## Delivery

### Delivery `finance_semantic_port`
- Kind: `semantic_port`
- Target: `finance/monthly-revenue`
- Description: Governed finance semantic port.

## Decisions

### Decision `aggregate_definition`
- Target: `model:monthly_customer_revenue`
- Status: `proposed`
- Provenance: `agent_authored`
- Ruling: Revenue is the sum of order amount_usd grouped by customer and month.

## Open Questions
```

This example is intentionally proposed. The approval operation writes the
content binding after the user confirms it.
