# Finance close

Core-tier B2 scenario (`tier: core`, `run_order: 8`) for month-end close
reconciliation. It checks hostile decimal parsing, exact-cent EUR
reconciliation, missing-weekend-FX handling, and superseding operator
decisions against a local mock close source.

## Scope

The source contains posted close entries in EUR, USD, GBP, and JPY. Amounts can
use thousands separators or parentheses for credits, and one weekend entry has
no FX rate. The agent must parse the representations, convert only rows with an
available rate, keep the missing-rate row visible as a warning, and never
present an unconverted amount as EUR.

The scenario deliberately changes the missing-FX decision mid-conversation.
The later decision supersedes the earlier decision in the decision history, but
does not change the EUR reconciliation rule or invent an exchange rate.

## Conversation

The answer sheet drives an eight-turn arc through input inspection, approval,
the missing-rate policy, intermediate checks, decision reversal, and final
reconciliation.

- **Turn 3** is a verbatim approval: exclude the weekend row with no FX rate,
  include rows with a rate, and reconcile in EUR cents. It also carries the
  hostile-decimal event, which warns that commas and parentheses are semantic.
- **Turn 4** records the initial `b2-weekend-fx` decision to exclude the row and
  flag the omission.
- **Turn 6** records `b2-weekend-fx-reversal`, which supersedes the first
  decision and preserves the unconverted source value without adding it to the
  EUR total. This turn carries the required
  `finance_close_reconciliation` plant.

The answer sheet's ground-truth brief explains that parentheses mean negative
amounts and that rounding belongs at the declared cents boundary. It does not
provide the computed total.

## Fixture

The scenario declares `dataset: finance_close`, `seed: 29`, and variant
`hostile-decimal-weekend-fx`. The `route_table` in `scenario.yaml` serves seven
close entries from `GET /close_entries`:

- EUR `1234.50` and EUR `85.00` use an FX rate of `1.00`.
- USD `1,250.00` at `0.92` becomes EUR `1150.00`.
- GBP `(200.00)` at `1.17` becomes EUR `-234.00`.
- USD `300.00` at `0.92` becomes EUR `276.00`.
- JPY `15000.00` at `0.0062` becomes EUR `93.00`.
- USD `(250.00)` on `2024-01-06` has no FX rate and is excluded from the
  EUR total while remaining a warning.

The committed reconciliation gold contains six landed rows, one excluded
missing-FX row, and `total_eur: "2604.50"`. The independent diagnostics gold
expects seven input rows, six converted rows, one missing rate, three weekend
closes, two negative amounts, and two parenthesized amounts.

## What is actually driven

`tests/test_scenario_finance_close.py` regenerates the deterministic fixture and
compares its committed gold byte-for-byte. The follow-up tests feed a structured
evidence object into the real `finance_close` checker, and a negative control
proves that a wrong total or missing-FX policy fails. The runner handover test
checks that the close endpoint and `evidence/finance_close.json` contract are
present.

The follow-up checker reads `evidence/finance_close.json`, not the agent's final
prose. Its `landed`, `promise`, `diagnostics`, and `decision_history` fields
are the package's evidence boundary.

## Execution

Run the package tests from `evals/dp-scenarios/`:

```bash
uv run pytest tests/test_scenario_finance_close.py -q
```

An optional local agent trial can exercise the conversation and mock-source
handover. It is not evidence from a real finance system or an authenticated
agent run unless the resulting artifact reaches and passes the follow-up gate:

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario finance-close \
  --epochs 1 \
  --output-dir /tmp/dp-scenarios-finance-close
```

## Goal

Reconcile the six convertible entries to exact-cent EUR values, retain the
missing-rate row as an explicit exclusion warning, preserve negative amounts,
and record both the initial decision and its later supersession. The latest
decision must not turn an unconverted value into a EUR amount.

## Assertions (`gates.follow-up.kind: finance_close`)

- Landed rows, the EUR total, and the count of excluded missing-FX rows must
  match the independent reconciliation gold exactly.
- The output promise must declare `comma_and_parentheses` parsing,
  `exclude_and_warn` for missing FX, an EUR total, and cents rounding.
- Reported diagnostics must match the independent counts for input, converted,
  missing-FX, weekend, negative, and parenthesized rows.
- Decision history must contain `b2-weekend-fx` and an entry named
  `b2-weekend-fx-reversal` whose `supersedes` value is the first decision.
- Missing or malformed landed data, promise, diagnostics, or decision history
  is `not-examined`, never a silent pass.

## Limitations

- **No real finance system or FX service.** The route table and all rates are
  fixed local data; the package does not validate production credentials,
  market-rate freshness, or a real close workflow.
- **No authenticated agent E2E is claimed.** The package tests drive the mock
  source and checker, not a completed live Claude session producing the
  evidence artifact.
- **No query gold is used for this drill.** The follow-up artifact is the
  evidence boundary, and the standard query gate is waived by declaration.
- **The reversal preserves an unconverted source value conceptually.** The
  graded EUR landed rows still exclude it, so the package does not test a
  second output column for unconverted amounts.
- **Repeatability is declared, not measured.** `scenario.yaml` declares five
  deterministic epochs and build-only observed-epoch certification; it does not
  claim that five live agent trials were run.
