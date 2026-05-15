# Migration Accelerator Workflow Pattern

Use this pattern to simulate the workflow of vendor migration accelerators while targeting a Nextdata mesh.

## Core Loop

1. **Collect** source artifacts: system metadata, samples, code, docs, diagrams, reports, team context, and constraints.
2. **Normalize** the evidence into an inventory with stable IDs, owners, domains, schemas, dependencies, freshness, and confidence.
3. **Classify** assets into candidate data product roles: source-aligned, domain, aggregate, serving, and context-document.
4. **Generate** first-pass local artifacts: mesh map, product candidates, and draft specs.
5. **Review** with humans: confirm ownership, product boundaries, schema confidence, schedules, and launch readiness.
6. **Validate** locally: syntax checks, available `nxd` validation, and explicit TODOs. Never launch from this skill.

## Decision Heuristics

- Prefer source-aligned products for raw systems, raw tables, files, or document sets with clear ownership.
- Promote to domain products when multiple assets describe a stable business concept owned by a team.
- Create aggregate products when data combines multiple upstream products for recurring analytics or decision workflows.
- Create serving products for reports, APIs, model features, agent tools, or app-specific outputs.
- Create context-document products when documents, policies, diagrams, or slide decks are business-critical context.

## Evidence Discipline

Every important inference needs evidence:

- Direct evidence: source schema, SQL, code, command output, file sample, confirmed user statement.
- Supporting evidence: repo names, folder names, report titles, BI dashboards, repeated column names, diagrams.
- Weak evidence: screenshots, isolated mentions, inferred ownership from naming only.

Do not collapse uncertainty. Record it in `mesh-inventory.json` and surface it in `product-candidates.md`.

## Output Standard

The first version is useful when it lets a delivery team answer:

- What assets exist?
- Who appears to own them?
- What data products should be built first?
- What inputs, outputs, contracts, schedules, and infra choices are known?
- What is still missing before validation or launch?
