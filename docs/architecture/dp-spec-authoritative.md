# Authoritative DP spec architecture

## Decision

The active DP specification is one canonical v2 Markdown document. It is the
editable source for the local job loop and the only document the generator may
compile. There is no active compatibility parser or migration layer for an
older spec.

The implementation is intentionally split into one core and thin entry points:

```text
dp-spec.md
  -> dp_spec_v2.py lossless parser + source map
  -> typed AST + section-specific diagnostics
  -> semantic content hash / diff / targeted patch / approval
  -> dp_diagnostics.py lock + build-record entry points
  -> nxd-generate-data-product consumes the approved AST
```

`dp_spec_version` values other than `2` fail with the stable
`unsupported_version` diagnostic. Historical benchmark records are evidence,
not runtime input.

## Markdown contract

Frontmatter contains `dp_spec_version`, `name`, `workflow`, and `status`.
Approved documents additionally contain `approved_content_hash`. The body has
these headings, in this order:

`Intent`, `Questions`, `Scope`, `Inputs`, `Models`, `Transform`, `Outputs`,
`Delivery`, optional `Contracts`, `Decisions`, `Open Questions`.

The section body is human Markdown: headings identify entities and labelled
bullets identify fields. It is not a YAML document hidden below Markdown
headings. Unknown sections, preambles, duplicate headings, and YAML-shaped body
lines are diagnosed rather than silently dropped.

## Semantic invariants

- Outputs are first-class. Each output references exactly one model, one or
  more questions, a projection, an ordering, and one or more deliveries. Every
  question reaches an output and every delivery is used.
- Contracts, when present, are typed entries bound to an Input or Output. Their
  inventory is recorded in the v2 lock and must match executable closure wiring.
- Each Model has exactly one origin: base/reference from an Input, derived from
  exactly one Transform producer, or a typed view expression. Each Transform
  step writes exactly one declared derived Model. The graph is acyclic.
- Transform operations are closed: `filter`, `project`, `derive`, `join`,
  `aggregate`, `union`, `deduplicate`, and `apply_procedure`. Field references
  are qualified. Join cardinality and unmatched behavior, aggregate null
  handling, union alignment/missing fields, and deduplicate ordering/winner
  behavior are required. Opaque SQL and free-form expressions are rejected.
- Procedures are versioned `id@version` references owned by a Transform step or
  reference Model. Decisions stores rationale/provenance and is never executable
  configuration. A top-level Policy section is invalid.
- Blocking Open Questions prevent approval and materialization.

## Editing and approval

The source map exposes stable paths such as
`v2:models[orders].description`. Targeted patches require the current semantic
base hash and preserve untouched source bytes, comments, and line endings. The
first release supports scalar/prose replacement; structural list/entity changes
are reviewed proposal edits. CRLF is rejected rather than normalized.

The content hash excludes lifecycle metadata. The explicit approval operation
validates the document, sets `status: approved`, and writes the matching
`approved_content_hash`. A semantic patch to an approved document atomically
sets `status: proposed` and removes the binding. The lock writer requires the
binding and copies the approved bytes unchanged into the closure.

## Claude Desktop form contract

Claude Desktop should prefill a reviewable document from the user's request,
render source-map paths as controls, show diagnostics inline, and keep Open
Questions visible. It should expose separate Propose, Approve, and Reject
actions. Canonical emit is a proposal only; the harness must not overwrite the
user's entire Markdown file.

## Versioned artifacts

The active identifiers are:

- `nxd-dp-spec-schema-v2`
- `nxd-dp-spec-canon-v2`
- `nxd-dp-spec-lock-v2`
- `nxd-build-record-v2`
- `nxd-diagnostic-report-v2`
- `nxd-dp-spec-diagnostic-v2`

The lock's `spec_hash` and the build record's `compiled_from` bind the closure to
the approved semantic content. Self-check and the generator must consume the
same hash and must never reparse an alternate specification shape.
