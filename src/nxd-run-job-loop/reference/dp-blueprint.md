# `dp-blueprint.md` — the user-owned plan between intent and a local data product

## Contents

- [Authoring contract](#authoring-contract)
- [Frontmatter](#frontmatter)
- [Sections](#sections)
- [Terms](#terms)
- [Interpretation and approval](#interpretation-and-approval)
- [Claude Desktop form contract](#claude-desktop-form-contract)
- [Worked example](#worked-example)

`dp-blueprint.md` is the document the user writes and edits. It is ordinary
Markdown with fixed top-level navigation and free prose inside each section.
The user is never expected to author or inspect the terse typed proposal used
by the compiler.

## Authoring contract

- Claude Desktop pre-fills the document from the request and source material;
  the user reviews and edits that prose rather than completing an empty schema.
- The only fixed syntax is the frontmatter and the ordered `##` headings below.
  Prose, lists, tables, examples, and code blocks are allowed inside sections.
- The authoring parser records headings, section text, and source spans. It does
  not interpret business meaning and it does not reject natural-language
  colons or list-shaped prose as pseudo-YAML.
- An external AI extraction step produces a typed proposal for deterministic
  validation. That proposal is an internal artifact, not a user-facing file.
- Missing information becomes an **Open Question**. The AI must not invent a
  behavior merely to satisfy a typed field.
- `status: approved` means the user approved the natural-language
  interpretation shown in the echo-back. Approval binds both the source hash
  and the exact typed proposal hash.
- Version 1 is unsupported. Version 3 is the prose-first authoring contract;
  the older v2 parser is retained only for read-only verification of existing
  v2 closure evidence while it remains present.

## Frontmatter

```yaml
---
dp_spec_version: 3
name: monthly_revenue
workflow: monthly-revenue
status: proposed
---
```

The required lifecycle fields are `dp_spec_version`, `name`, `workflow`, and
`status`. An approved document also carries `approved_content_hash` and
`approved_proposal_hash`. When an approved document is edited, the resulting
`status: proposed` document retains `prior_approved_proposal_hash`; the next
approval must supply that prior typed snapshot so locked Decisions cannot be
silently replaced. Lifecycle fields are excluded from the source semantic
hash.

## Sections

The document has exactly these top-level headings, in this order:

1. **Intent** — the outcome, audience, and desired use.
2. **Questions** — the natural-language questions the product should answer.
3. **Scope** — inclusions, exclusions, grain boundaries, and assumptions.
4. **Terms** — definitions used by this document and the product.
5. **Inputs** — source material and expectations about accepted data.
6. **Models** — named relations or concepts needed by the result.
7. **Transform** — business logic, joins, aggregation, procedures, and model
   orchestration. Decisions belong here when they affect computation.
8. **Outputs** — user-visible products and promises about their behavior.
9. **Decisions** — rationale and provenance for explicit decisions that can be
   locked after approval.
10. **Open Questions** — unresolved questions, their target, and whether they
    block approval or materialization.

There is deliberately no user-authored `Delivery` section: local DPs currently
produce a DuckDB-backed semantic-query result. There is no user-authored
`Contracts` section: executable contracts are compiled internally from Input
expectations and Output promises. A request for unsupported delivery is an
Open Question, not a user-selectable transport setting.

## Terms

Terms are inline. A term may use a simple `###` heading and natural prose:

```text
## Terms

### Customer

A customer is the person or organization responsible for an order.
Also known as an account holder. Examples include a company buying a plan.
```

The extraction layer derives a stable local id and NXD-compatible metadata:
`name`, `definition`, `synonyms`, `related_terms`, `examples`, `term_values`,
`priority`, and an NXD glossary string-to-string `tags` map. `related_terms` must resolve to another
term in this document. External glossary DPs, URLs, and implicit external
definitions are not supported. Omitted priority uses NXD's P3 default and is
disclosed in the echo-back.

## Interpretation and approval

The lifecycle is:

```text
Markdown structure and spans
  → AI typed proposal with provenance
  → deterministic validation
  → natural-language echo-back and Open Questions
  → user approval
  → self-contained closure snapshots
```

Every approval-relevant typed value records `explicit`, `inferred`, or
`platform_fixed` provenance. Inferred values must be covered by the echo-back.
Blocking Open Questions prevent approval.

Each approved Decision is locked by id and hash. Extraction cannot overwrite a
locked Decision. A conflicting edit becomes an explicit proposed change and
revokes the approval; it is never silently merged.

Formatting-only edits may retain approval only after re-extraction proves the
typed proposal is unchanged. Behavioral edits, Terms edits, contract-inventory
edits, or delivery-profile changes require a new approval. The closure stores
the byte-identical `dp-blueprint.approved.md` and the approved typed proposal JSON;
it never points back to the live document.

## Claude Desktop form contract

The form layer should:

- show the prefilled Markdown/read-back before asking for field completion;
- group controls by the same section order as this document;
- use stable paths such as `v3:inputs[orders].text` and source spans for inline
  diagnostics and focused edits;
- keep inferred values and Open Questions visible;
- offer **Propose**, **Approve**, and **Reject** actions separately;
- disable approval while validation errors or blocking Open Questions remain;
- apply stale-hash-checked targeted patches or present a reviewed proposal;
- never replace the whole user document with a canonical typed emit.

## Worked example

```markdown
---
dp_spec_version: 3
name: monthly_revenue
workflow: monthly-revenue
status: proposed
---

## Intent

Provide an auditable monthly revenue relation for finance review.

## Questions

What was monthly revenue for each customer and month?

## Scope

Include completed paid orders. Exclude refunds until their timing rule is
decided.

## Terms

### Customer

A person or organization responsible for an order. Also known as an account
holder.

## Inputs

### Orders

Load completed orders from the monthly export.

#### Expectations

Rows have an order identifier. Amounts are expressed in EUR.

## Models

### Monthly revenue

Revenue grouped by customer and month.

## Transform

Group accepted orders by customer and month and sum their amounts. Apply the
refund decision here when its timing rule is answered.

## Outputs

### Monthly revenue by customer

The user-visible monthly revenue relation.

#### Promises

Refunds are excluded and accepted rows reconcile to the result.

## Decisions

### Refund treatment

Exclude refunds until a timing rule is supplied.

## Open Questions

When should refunds be applied? This blocks approval of the output.
```

The AI should echo the interpretation and ask the refund question before
approval. It should not ask the user to inspect the typed proposal.
