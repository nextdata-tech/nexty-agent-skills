# Scenario: Co-author a scored data product from a supplied rubric

I have 10 applicants exported to `data/applicants/applicants.csv`. I want a
local desktop data product that screens and scores them so I can query the
results.

## My gates

An applicant must clear all of these to be scorable:

- **G1 portfolio** — a real portfolio URL is captured. A skills list that merely
  claims backend work is not evidence; it must be a URL.
- **G2 backend** — the applicant does backend engineering.
- **G3 seniority** — 4 or more years of experience.

## My rubric

Score each scorable applicant on these criteria, 1 to 5:

| criterion | weight |
|---|---|
| depth of backend experience | 50 |
| relevance of education | 30 |
| breadth of stack | 20 |

On depth of backend experience, 5 means 10+ years and 1 means under 2 years.
On breadth of stack, 5 means four or more distinct technologies and 1 means one.

## My verdicts

- **ADVANCE** — weighted total of 4.0 or above
- **HOLD** — weighted total of 2.5 or above
- **REJECT** — below that

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
