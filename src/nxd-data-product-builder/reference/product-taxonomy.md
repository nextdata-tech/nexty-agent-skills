# Data Product Type Taxonomy & Evidence Discipline

Use this reference to classify a candidate into a data product role and to keep
inferences grounded in evidence while building it.

## Data Product Types

Classify each candidate into one of five roles:

1. **Source-aligned** — reads from one raw system, table, file set, or document
   set with clear ownership and writes a near-identical model (rename, reformat,
   repartition — not reshape).
2. **Domain** — multiple assets describe a stable business concept owned by a
   single team; promote them into one domain product.
3. **Aggregate** — combines multiple upstream products for recurring analytics
   or decision workflows (aggregations, joins, derived metrics).
4. **Serving** — reports, APIs, model features, agent tools, or app-specific
   outputs shaped for a particular consumer.
5. **Context-document** — documents, policies, diagrams, or slide decks that are
   business-critical context rather than tabular data.

## Decision Heuristics

- Prefer **source-aligned** products for raw systems, raw tables, files, or
  document sets with clear ownership.
- Promote to a **domain** product when multiple assets describe a stable
  business concept owned by a team.
- Create an **aggregate** product when data combines multiple upstream products
  for recurring analytics or decision workflows.
- Create a **serving** product for reports, APIs, model features, agent tools,
  or app-specific outputs.
- Create a **context-document** product when documents, policies, diagrams, or
  slide decks are business-critical context.

## Evidence Discipline

Every important inference needs evidence:

- **Direct evidence:** source schema, SQL, code, command output, file sample,
  confirmed user statement.
- **Supporting evidence:** repo names, folder names, report titles, BI
  dashboards, repeated column names, diagrams.
- **Weak evidence:** screenshots, isolated mentions, inferred ownership from
  naming only.

Do not collapse uncertainty. Record it explicitly — mark it with a `TODO`
marker in the spec or note it in the build's open-TODO ledger
(see [state-and-resume.md](state-and-resume.md)) — and surface it to the user.

## Output Standard

A first-pass classification is useful when it lets a delivery team answer:

- What assets exist?
- Who appears to own them?
- What data product should be built, and as which type?
- What inputs, outputs, contracts, schedules, and infra choices are known?
- What is still missing before validation or launch?
