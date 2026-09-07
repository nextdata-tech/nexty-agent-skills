# Parent-child grain trap

Smoke-tier scenario (`tier: smoke`, `run_order: 2`) for a parent-grain revenue
aggregation. It catches the error where joining line items multiplies an
order-level amount by the number of child rows.

## Scope

The operator asks which regions are bringing in money without naming the
source, grain, join, or aggregation. The agent must discover and record that an
order is the unit contributing `order_amount` once. Line-item `product` is
descriptive and does not change the required regional revenue result.

## Conversation

The answer sheet drives a seven-turn arc through definition, build, checks,
result, reconciliation, and final review. The operator answers source and
business-definition questions from the script, and uses a ground-truth brief
for field-semantics questions the script does not cover.

Turn 5 injects the required `grain_trap_fanout` event: it asks for a result
broken out by region and product, one line per combination. The event must be
observed before the follow-up check is allowed to grade the closure. The
opening message is checked separately to ensure it does not leak the answer.

## Fixture

The runner generates `dataset: grain_trap` with seed `29` and variant
`seeded-parent-child` for each trial:

- `orders` span north, south, east, and west. Each active order has one through
  five related line items, creating the fan-out trap.
- Deleted orders are excluded, and three orphan line-item keys do not create
  parent orders.
- Synthetic markers remain in the fixture so the common leakage checks stay
  active.

The independent active-order control total is `7260.34`. The gold row set has
one exact-cent `regional_revenue` value per region: east `1602.82`, north
`1751.14`, south `1402.98`, and west `2503.40`. The diagnostics gold also
contains the expected naive fan-out values so that wrong answers caused by
child multiplication are classified separately from other wrong answers.

## What is actually driven

`tests/test_scenario_parent_child_grain_trap.py` regenerates the source CSVs,
recomputes the active-order total independently, and verifies every committed
gold artifact byte-for-byte. It also feeds a semantic closure and query rows to
the real follow-up checker. The checker reads the named `semantic.json`
document, requires `semantic.grain: order` and
`semantic.metrics.regional_revenue.aggregation: sum`, and uses the deterministic
EX scorer for the query gold.

The acceptance tests do not invoke a live agent, supervisor build, or governed
query over a running desktop product. They test the evidence and oracle paths
that a live run would later populate.

## Execution

Run the package tests from `evals/dp-scenarios/`:

```bash
uv run pytest tests/test_scenario_parent_child_grain_trap.py -q
```

An optional local agent trial can exercise the conversation and desktop
handover:

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario parent-child-grain-trap \
  --epochs 1 \
  --output-dir /tmp/dp-scenarios-parent-child-grain-trap
```

Treat a result as scenario evidence only when the required plant is observed,
the closure is examined, and the query gate receives the agent's actual result.

## Goal

Define the output at order grain, sum each active order amount once, exclude
deleted orders and orphan children, and return the four exact-cent regional
values. A child-fan-out answer must be rejected as `expected_naive_fanout`.

## Assertions (`gates.follow-up.kind: grain_and_aggregation`)

- The opening prompt contains no source, join, grain, aggregation, or expected
  number that gives away the difficulty.
- The named semantic document declares grain `order` and uses `sum` for
  `regional_revenue`.
- Supervisor-owned build facts identify a published release. Fixture source
  table counts and built model counts are not compared because they measure
  different objects; any claimed counts are checked against supervisor facts
  by ledger lint.
- Governed query rows match `gold/grain_trap_by_region.json`, and their values
  sum to the independent `7260.34` control total.
- The deterministic scorer distinguishes the expected naive fan-out result
  from other wrong results.
- The required plant fires before the follow-up is graded. Missing plant or
  malformed closure/query evidence is `not-examined`, never a silent pass.
- The common ledger, phase, sentinel, route, and other applicable gates remain
  clean.

## Limitations

- **No live agent or hosted CI E2E is claimed by the package tests.** They verify
  generated fixtures, evidence parsing, and deterministic scoring rather than
  a completed agent build and query.
- **The required answer is regional revenue only.** The planted request for a
  region-by-product result tests scope handling; product-level output is not a
  second accepted gold contract.
- **The control total is seed-specific.** Changing the declared seed changes
  the generated rows and expected gold; the test recomputes the control for
  that seed rather than treating `7260.34` as universal.
- **Repeatability is declared, not measured.** `scenario.yaml` declares five
  deterministic epochs and Wilson certification for build and query, but the
  package tests do not run five live agent trials.
