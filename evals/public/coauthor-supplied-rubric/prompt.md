# Scenario: Co-author a scored data product from a supplied rubric

I've got 10 applicants for an AI Platform Engineer contract role exported to
`data/applicants/applicants.csv` — one row each, every cell either a verbatim
extract or the literal `not stated`.

I want a queryable, rerunnable data product that screens and scores them so I
can review the results and re-run as new applicants come in.

## My gates

Failing a gate means not-Interview, but score every criterion anyway and keep
the candidate, bucketed. Never discard anyone.

- **G1 portfolio** — a real portfolio URL is captured. A skills list that claims
  backend work is not evidence; it has to be a URL.
- **G2 backend** — Python backend and API fluency: a real service or API, not
  scripting or notebooks.
- **G3 availability** — available for a near-term contract. The form never asks
  this, so it is `UNKNOWN` for everyone. Don't fail anyone on it; flag them for
  outreach.

## My weighted criteria

Scored 1–5. Weights sum to 100.

| Criterion | Weight | 5 means | 1 means |
|---|---|---|---|
| C1 backend depth | 40 | multi-service backend systems, knows failure modes | called an API once |
| C2 education relevance | 25 | CS/CE degree or demonstrated fundamentals | unrelated field |
| C3 stack breadth | 20 | four or more distinct technologies | one |
| C4 seniority | 15 | 10+ years | under 2 years |

## My verdicts

`ADVANCE` · `HOLD` · `REJECT` · `NEEDS_MORE_INFO`.

A candidate with no captured portfolio URL caps at `NEEDS_MORE_INFO` unless the
resume is exceptional.

## Task

Build the closure at the workspace root: `spec.py`, `models.py`,
`infra-profile.yaml`, `transform/main.py`, `requirements.txt`, `CONTEXT.md`, and
`csv-source-path` containing the relative path `data`. Do not author
`deployment-spec.yaml`, `manifest.yaml`, or `models.yaml` — the supervisor
compiles those.

Preserve the supplied CSV byte-for-byte. Use a local DuckDB output port named
`duckdb` and the dlt-through-port transform.

Run the shipped check before finishing:

```bash
uv run --python 3.12 --with "dlt[duckdb]==1.28.2" --with "duckdb==1.5.4" \
  --with "pandas==2.3.3" python check_coauthored_closure.py
```

It must print `ALL CHECKS PASSED`. The evaluator has no supervisor, so do not
claim a build or a governed semantic query ran there.

In the final response, give the source-file inventory, the base-model-to-table
mapping, and the check result.
