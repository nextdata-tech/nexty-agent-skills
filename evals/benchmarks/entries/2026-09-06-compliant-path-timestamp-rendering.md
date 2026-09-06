---
id: 2026-09-06-compliant-path-timestamp-rendering
date: 2026-09-06
label: "stop a database's timestamp rendering reading as a wrong pipeline"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — stop a database's timestamp rendering reading as a wrong pipeline

## Notes

Harness grading only; no skill under `src/` changes, so no runnable public arm
can distinguish it.

**How it surfaced.** The first live `crm-pipeline` run to route through
`nxd-generate-data-product` — the run where the conduct-rule and prompt fixes
finally worked — regressed `follow-up` from PASS to
`pipeline_output_disagrees_with_independent_gold`. The rows were correct. Every
`deal_id`, `stage` and `amount` matched the committed gold, the tombstoned
`DEAL-2006` was excluded, and the row order was identical. The only difference
was how a timestamp was spelled:

| source | `updated_at` |
|---|---|
| governed `run_semantic_query` | `2024-01-05 10:00:00+00` |
| committed gold | `2024-01-05T10:00:00+00:00` |

Same instant. `crm_pipeline.py` compared the row dicts with `!=`, so the
database's own text rendering read as a wrong pipeline.

**Why this is the same family as the construction defects.** The comparison
passed only for an agent that *hand-authored* its evidence into the gold's
spelling, and failed the agent that copied what the product actually returned.
The three earlier runs passed `follow-up` for exactly that reason. So the gate
rewarded the non-compliant path and punished the compliant one — which is what
every defect fixed on this branch has in common.

**The fix is narrow.** Only fields in `_INSTANT_FIELDS` (`updated_at`) are
normalised, and only by parsing to a `datetime`; `deal_id`, `stage`, `amount`,
the key set and the row order still compare exactly. An unparseable value is
returned unchanged so it compares unequal rather than quietly matching. A
genuinely different instant is still a disagreement.

## Evidence

- `evals/dp-scenarios/tests/test_scenario_crm_pipeline.py` — the live rendering
  passes; a different instant and an unparseable timestamp both still report
  `pipeline_output_disagrees_with_independent_gold`. The first fails against
  the previous implementation.
