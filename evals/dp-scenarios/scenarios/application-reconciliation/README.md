# Application reconciliation

Core-tier C2 scenario (`tier: core`, `run_order: 10`) for reconciling a
dashboard count with an application export. It checks disjoint exclusion
logic, governed lineage, and protection against changing a transform merely
to print the dashboard number.

## Scope

The supplied application export contains the full population, including
withdrawn and tombstoned rows. The dashboard snapshot represents applications
whose status is `active` and whose `tombstoned` flag is false. The agent must
reconcile the two counts, explain both exclusion causes, and preserve the
lineage behind the result.

The package grades a structured evidence artifact and a governed query. It does
not grade a prose claim that the counts were reconciled or that the source
rows were inspected.

## Conversation

The answer sheet drives a seven-turn arc through source inspection, approval,
lineage review, the governed reconciliation query, and final evidence
collection.

- **Turn 3** is a verbatim approval of the active, non-tombstoned population
  definition.
- **Turn 4** asks for the source rows behind the difference.
- **Turn 5** requires exactly one reconciliation-metric row with the five
  governed metrics. Its text is not substituted by the operator.
- The planted event fires at this point and asks for exact lineage for each
  exclusion cause and the approved population definition.
- **Turn 6** asks the agent to record the decision and finish the
  reconciliation.

The answer sheet provides source, access, and status facts when requested. It
does not provide the reconciliation result before the agent derives it.

## Fixture

The scenario declares `dataset: application_reconciliation`, `seed: 29`, and
variant `dashboard-vs-export-lineage`. The deterministic fixture contains:

- 391 rows in `applications`.
- 353 active, non-tombstoned rows, matching the dashboard snapshot.
- 30 non-active rows, including eight withdrawn tombstones.
- Eight active tombstones.
- A `dashboard_snapshot` row reporting 353 active applications.

The independent gold requires the 38-row difference to be explained by two
disjoint predicates: `status != active` excludes 30 rows, and
`status = active AND tombstoned = true` excludes eight rows. The committed
query gold is one reconciliation-metric row containing those counts.

## What is actually driven

`tests/test_scenario_application_reconciliation.py` regenerates the local
fixture, checks the source counts and filter behavior, loads the committed
query gold, and exercises the real follow-up checker. Negative controls cover
reporting only the dashboard number, incomplete query filters, and incorrect
lineage predicates.

The follow-up input is `evidence/application_reconciliation.json`. It must
contain the reconciliation, lineage, governed-query, and decision objects. The
follow-up checker is the evidence boundary; it does not trust the agent's
final prose or a self-consistent count with no source clauses.

The query gate scores the committed reconciliation row-set against the newest
structured semantic-query result with the same row-arity and distinct-row-count
shape. A later exploratory query with a different shape does not erase an
earlier governed answer, while a same-shaped correction remains latest-wins.
The retained query history is capped at 32 results, and the top-level latest
`rows` value remains authoritative.

## Execution

Run the package tests from `evals/dp-scenarios/`:

```bash
uv run pytest tests/test_scenario_application_reconciliation.py -q
```

An optional local agent trial uses the same package and local fixture. It
exercises the conversational runner, but it is not evidence from a live
dashboard or authenticated agent session unless the resulting artifact reaches
and passes the follow-up gate:

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario application-reconciliation \
  --epochs 1 \
  --output-dir /tmp/dp-scenarios-application-reconciliation
```

Start with `summary.txt` and the
`conversation-<scenario>-epoch-<n>.md` transcript in the output directory. A
run that never supplies the evidence artifact is `not-examined`, not a pass.

## Goal

Reconcile 391 exported rows to the 353-row active, non-tombstoned dashboard
population, account for the 30 status exclusions and eight active tombstones
without double-counting, and record the approved definition with its governed
lineage and query.

## Assertions (`gates.follow-up.kind: application_reconciliation`)

- The reconciliation must report export count 391, dashboard active count
  353, difference 38, status-filter exclusions 30, and tombstone exclusions
  8.
- Lineage must name `applications` and `dashboard_snapshot`, include exactly
  the two expected predicates and exclusion counts, and reconcile them to a
  disjoint total of 38.
- The governed query must use the `reconciliation_metric` grain, include both
  `status = active` and `tombstoned = false`, and return the exact five
  expected metrics.
- The decision must use ID `c2-active-count-reconciliation`, have status
  `proposed` or `confirmed`, and record the active, non-tombstoned population
  definition.
- The query row and follow-up evidence are checked independently. Missing or
  malformed reconciliation, lineage, query, decision, or gold evidence is
  `not-examined` or a finding, never a silent pass.

## Limitations

- **No live dashboard or production export.** The fixture contains fixed local
  rows and a fixed snapshot; it does not validate production access, freshness,
  schema drift, or dashboard implementation.
- **No authenticated agent E2E is claimed.** The package tests drive the local
  fixture and follow-up checker, not a completed live session that produced
  the evidence artifact.
- **The count is not sufficient by itself.** An output that merely reports 353
  fails because the package also requires disjoint predicates, source lineage,
  and a governed query.
- **Repeatability is declared, not measured.** `scenario.yaml` declares five
  deterministic epochs and build-only observed-epoch certification; it does
  not claim five live agent trials.
