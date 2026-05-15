# Domain & Subdomain Intake

Phase 2 of the wizard. Goal: produce `domain-map.md` and a `domains` array in `mesh-inventory.json`. Domains drive product ownership, infra-profile boundaries, and downstream candidate clustering.

## Intake order

1. Ask: "Do you have a domain map (image, PDF, slide deck, markdown table)?"
2. If yes → file ingest path. If no → Q&A path. If partial → ingest what exists, mark gaps as TODOs.

## File ingest

| Format | How to read |
|---|---|
| PNG / JPG / SVG | `Read` tool (multimodal) — extract domain names + subdomain groupings from labelled clusters. |
| PDF | `Read` tool with a `pages` range — usually the domain slide is one page; ask the user which page if unclear. |
| Markdown | `Read` + `Grep` for `\|\s*[A-Z]` table rows; or hand-extract bullet trees. |
| PowerPoint | Ask the user to export the relevant slide as PNG/PDF first. |

After extraction, **always** show the inferred tree to the user and ask: "Does this match how the business describes domains today?" Confirm before persisting.

### Example: argenx domain map

Input: `docs/domains/domains.png` — six labelled clusters around grouped subdomain bubbles.

Inferred tree:

```
Research:           [Discovery, Translation Science, IIP]
Development:        [Clinical Trial Operations, Regulatory, GDS]
Commercial:         [Medical Affairs, Market Access, HCP Experience, US, Intl, Japan]
TechOps & Quality:  [Supply Chain, CMC, Quality]
G&A:                [HR, Finance, Corp. Dev. & Strategy]
```

Each domain entry → one record in `mesh-inventory.json#/domains` with `confidence: medium` (visual-only inference unless corroborated).

## Q&A path

When no artifact exists, walk the user one prompt at a time:

1. "What are the top-level business or technical domains today?" — capture names, expect 3–8.
2. For each domain: "What subdomains, capabilities, or sub-teams sit under `<domain>`?"
3. For each: "Who owns it? Producer team, steward, accountable VP/Director?"
4. "Do any domains span multiple business units or share infrastructure?"

Suggest common shapes only if the user is stuck — never auto-fill. Examples to prompt with:

- Pharma R&D-led: Research / Development / Commercial / TechOps / G&A
- Tech-led: Platform / Product / Marketing / Sales / Finance / People
- Bank-led: Retail / Wholesale / Markets / Risk / Compliance / Ops

## Partial / unknown

If the user says "I'm not sure about subdomains under Commercial", record what they have and add to `open-todos.md`:

```markdown
- [ ] phase: domain-map | item: subdomains under Commercial | blocker: user unsure | added: 2026-05-06
```

The wizard re-surfaces the row on resume.

## Domain record structure

Every domain entry in `mesh-inventory.json#/domains` carries:

```json
{
  "name": "Commercial",
  "parent": null,
  "kind": "business|technical|cross-cutting",
  "owner_team": "Commercial Data",
  "steward": null,
  "evidence": ["evidence:domain-map-png"],
  "confidence": "medium",
  "notes": "Subdomains span US, Intl, Japan — geo split."
}
```

Subdomains use `parent` = parent domain name. Avoid more than two levels of nesting in v1.

## domain-map.md template

```markdown
# Domain Map

> Source: <file path or "Q&A 2026-05-06">

## Top-level domains

- **Research** — owner: Research Data Team. Evidence: `domains.png`.
  - Discovery
  - Translation Science
  - IIP
- **Development** — owner: Clinical Operations.
  - Clinical Trial Operations
  - Regulatory
  - GDS
- ...

## Open questions

- Pulled from `open-todos.md`, filtered by `phase: domain-map`.
```

## Boundary checks before exiting Phase 2

- No two domains share a name (case-insensitive).
- No subdomain appears under more than one parent.
- Every domain has an evidence reference (or `confidence: low` + a TODO row).
- The user has explicitly confirmed the tree, OR the wizard has logged "user deferred confirmation" as a TODO.
