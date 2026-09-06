# Parent-child grain trap

## Goal

Verify that the agent defines the result at the parent order grain and does
not multiply a parent amount by the number of related child rows. The expected
regional revenue must count each active order's amount exactly once.

## Fixture

The runner generates the `grain_trap` dataset with seed `29` and the
`seeded-parent-child` variant for every trial:

- `orders` contains parent records across north, south, east, and west.
- Each order has one through five line items, creating a deliberate fan-out
  trap.
- Deleted orders must be excluded.
- Three orphan line-item keys must not create orders.
- Synthetic marker values are included so leakage checks remain active.

The independent control total for the committed seed is `7260.34`. The gold
row set contains one exact-cent `regional_revenue` value per region. The
diagnostics also retain the expected naive fan-out values so the grader can
classify that specific wrong answer separately from other wrong answers.

## Conversation and execution

The operator opens with a vague question about which regions are bringing in
money. It answers source and business-definition questions the agent asks
from the scripted answer bank, and column-semantics questions the bank does
not cover (for example, what `order_amount` means at the order vs. line-item
grain, or whether `product` matters for the revenue figure) from a declared
`ground_truth` brief. A question that neither the answer bank nor the brief
covers gets the operator's honest "I don't know, you tell me" fallback rather
than a scripted line that happens to not address it. The operator then drives
the build, checks, result, reconciliation, and final-check phases. A planted
scope-creep event exercises the grain difficulty.

The agent under test is expected to use the Nexty job-loop and `nxd-desktop`
MCP flow to author the closure, validate it, build/publish it, serve it, and
run a governed semantic query.

## Assertions

- The opening prompt does not reveal the source, join, grain, aggregation, or
  expected numbers.
- The built semantic artifact declares grain `order`.
- `regional_revenue` uses `sum` at that grain.
- Supervisor-owned build facts identify a published release. Row counts are
  not compared against the fixture: the fixture counts source *tables* and the
  supervisor counts built *models*, and this scenario's point is that the built
  model must not preserve the child grain, so no such equality could hold.
  Whether the agent's own ledger claims match the supervisor's counts is
  checked by ledger lint.
- Governed query rows match the committed gold row set using the deterministic
  EX scorer.
- The regional result reconciles to the independent control total.
- The known child-fan-out answer is classified as `expected_naive_fanout`, not
  accepted as correct.
- The planted grain difficulty fires before the follow-up check is graded.
- Ledger honesty, phase accounting, sentinel scanning, and the applicable
  common gates remain clean.

This scenario uses the local desktop runtime. It does not currently assert a
hosted CI live E2E or a judge-model assessment of the agent's prose.
