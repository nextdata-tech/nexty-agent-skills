# Locale and timezone

Core-tier C6 scenario (`tier: core`, `run_order: 11`) for preserving
non-ASCII source values and separating source-local reporting days from UTC
audit timestamps. It checks timezone-boundary arithmetic, daily aggregation,
and exact Unicode query behavior around the America/New_York DST transition.

## Scope

The activity source carries explicit source-local timestamps, UTC timestamps,
amounts, categories, and a declared source timezone. The agent must choose the
source-local day boundary for reporting, retain UTC for audit, compare both
daily interpretations, and preserve category values exactly.

The package grades structured policy, reconciliation, diagnostics, and query
evidence. It does not grade a prose claim that timezone conversion or Unicode
handling was correct.

## Conversation

The answer sheet drives an eight-turn arc through source inspection, approval,
daily comparison, the planted boundary event, an exact Unicode query, and final
evidence collection.

- **Turn 3** is a verbatim approval to use the source-local timezone for daily
  reporting, retain UTC for audit, and preserve original categories.
- **Turn 4** asks the agent to continue with the daily comparison.
- **Turn 5** asks what changes at the timezone boundary and carries the
  planted event requiring both day-boundary views and the original non-English
  values to remain queryable.
- **Turn 6** requires exactly one row for the Japanese category. Its text is
  not substituted by the operator.
- **Turn 7** asks the agent to record the decision and finish the view; the
  final turn asks for the current status.

The answer sheet provides source, access, and status facts when requested. It
does not provide the daily totals or category count before the agent derives
them.

## Fixture

The scenario declares `dataset: locale_timezone`, `seed: 29`, and variant
`utf8-dst-boundary`. The deterministic fixture contains 14 events, seven with
the category `Renovación` and seven with the exact category `契約`.

All events declare `America/New_York`. The fixture crosses the March 2024 DST
transition, and one event is on March 10 in the source-local day while its UTC
representation is on March 11. The independent reference requires:

- source-local and UTC totals of `2310.00`;
- 12 local reporting days and 12 UTC reporting days;
- one shifted row, or `0.07142857` of the 14 rows;
- exact source-local and UTC daily row counts and amounts; and
- one query row for `契約` with `row_count: 7`.

The committed query gold contains that exact Unicode category row. The
reconciliation and diagnostics golds independently capture the timezone,
daily series, totals, shift, and query facts.

## What is actually driven

`tests/test_scenario_locale_timezone.py` regenerates the local fixture, checks
the non-ASCII values and DST offsets, verifies the recorded UTC values are
derived from local timestamps, loads the committed query gold, and exercises
the real follow-up checker. Negative controls cover wrong daily amounts,
missing Unicode values, and an incorrect UTC derivation.

The follow-up input is `evidence/locale_timezone.json`. It must contain the
time policy, both daily comparisons, the exact Unicode query, and the decision
object. The follow-up checker is the evidence boundary; it does not trust the
agent's final prose or row counts without the corresponding daily amounts.

The query gate scores the committed Japanese-category row-set against the
newest structured semantic-query result with the same row-arity and
distinct-row-count shape. A later exploratory query with a different shape
does not erase an earlier governed answer, while a same-shaped correction
remains latest-wins. The retained query history is capped at 32 results, and
the top-level latest `rows` value remains authoritative.

## Execution

Run the package tests from `evals/dp-scenarios/`:

```bash
uv run pytest tests/test_scenario_locale_timezone.py -q
```

An optional local agent trial uses the same package and local fixture. It
exercises the conversational runner, but it is not evidence from a live
regional source or authenticated agent session unless the resulting artifact
reaches and passes the follow-up gate:

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario locale-timezone \
  --epochs 1 \
  --output-dir /tmp/dp-scenarios-locale-timezone
```

Start with `summary.txt` and the
`conversation-<scenario>-epoch-<n>.md` transcript in the output directory. A
run that never supplies the evidence artifact is `not-examined`, not a pass.

## Goal

Use `America/New_York` source-local days for reporting, retain UTC for audit,
reconcile both daily views and their invariant total, preserve the one
boundary-shifted event, and return the exact non-ASCII category count.

## Assertions (`gates.follow-up.kind: locale_timezone`)

- The policy must preserve `America/New_York`, select `source_local` as the
  daily boundary, and retain UTC for audit.
- Source-local and UTC totals must both be `2310.00`, totals must be invariant,
  and the two daily arrays must match the independent row counts and amounts.
- The comparison must report one boundary-shifted row and the exact fraction
  `0.07142857`.
- The Unicode query must preserve `契約` exactly and report row count 7.
- The decision must use ID `c6-source-local-day`, have status `proposed` or
  `confirmed`, and record the source-local day boundary with UTC as audit
  representation.
- The query row and follow-up evidence are checked independently. Missing or
  malformed policy, comparison, Unicode query, decision, or gold evidence is
  `not-examined` or a finding, never a silent pass.

## Limitations

- **No live regional source.** The fixture has fixed timestamps, amounts,
  categories, and timezone declarations; it does not validate production
  locale data, timezone metadata, or daylight-saving policy.
- **No authenticated agent E2E is claimed.** The package tests drive the local
  fixture and follow-up checker, not a completed live session that produced
  the evidence artifact.
- **Totals alone are insufficient.** The package also checks both daily
  groupings, the boundary shift, and the exact Unicode query so a pipeline
  cannot hide a date or encoding error behind an unchanged grand total.
- **Repeatability is declared, not measured.** `scenario.yaml` declares five
  deterministic epochs and build-only observed-epoch certification; it does
  not claim five live agent trials.
