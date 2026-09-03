# SIGTERM diagnosis

Second core-tier (`tier: core`) scenario, `run_order: 4`. It is the first
consumer of `src/dp_scenarios/knobs/` — until now that unit was fully tested
but had no caller outside its own tests, which is the condition under which a
unit's tests quietly start asserting its own self-report instead of a
property.

## Which planning scenario this is

`10 Tiers, merges, and build order.md`'s naming table maps `sigterm-diagnosis`
onto **S3-smoke**. Note 03's S3 is titled "Budget-bound source plan
(NEX-874 / NEX-888)", which reads at first like a budget scenario rather than
a signal one, but its body settles it: *"the ceiling is a SIGTERM with no
staging marker, no useful stderr"*, and the graded difficulty is that the
agent must distinguish (a) a client RPC deadline, (b) a supervisor transform
timeout, and (c) a genuine hang. The name matches the planted difficulty, not
the title. B8 (`timeout-diagnosis`) is the full-tier heir and is not built
here.

## Fixture

`dataset: grain_trap`, `seed: 29`, variant `mock-rest-order-fetch-sigterm` —
the same generated `orders`/`line_items` shape the other scenarios use, so
no new dataset is introduced. The planted difficulty is a **plan** property,
not a row-count property:

- The naive plan fetches orders one at a time: 20 orders (4 regions × 5,
  seed-independent) at a fixed 50 ms server-side per-call latency.
- The bounded plan issues a single server-side `status=active` query, which
  returns every matching row in one page: 1 call regardless of row count.
- `active_order_count` is 18 — the 20 orders minus the `tombstones` injector's
  `floor(0.10 × 20) = 2` rows marked `status=deleted`. The injector's count is
  fixed; only *which* rows it picks is randomized.

The overrun is guaranteed **by construction**, per note 03's determinism
requirement that it never depend on raw row counts:
`knobs.TransformWindowSizing.from_plans` derives the transform window from the
two plans and proves the naive plan exceeds twice that window while the
bounded plan stays at or under half of it. On any hardware.

## Execution

Deterministic/replay path only. Evidence is graded through
`Scenario.follow_up_check`; the scenario declares `has_scoreable_answer_gold`
`False` and certifies the `build` gate under a Wilson lower bound of 0.90 at
95% confidence over 5 epochs.

## Goal

The agent must read the run record before acting, attribute the kill to the
supervisor transform window rather than to memory, a client deadline, or a
code bug, and fix it by narrowing the source-side query — not by truncating
the result set until it fits.

## Assertions (`gates.follow-up.kind: sigterm_diagnosis`)

- **The two attempts really are what the record says:** the naive attempt is
  SIGTERM-killed (`outcome: sigterm`, `signal: 15`) and the bounded attempt
  completes. A record claiming otherwise is wrong evidence, not a stylistic
  difference.
- **The call arithmetic is reconciled, not trusted:** the declared call counts
  and latency are checked against the committed gold *and* re-derived through
  `TransformWindowSizing.from_plans`. A target could otherwise report
  `bounds_hold: True` for numbers the fixture never generates.
- **Landed rows equal the oracle under the declared filter:** the bounded
  attempt must land 18 rows — the orders satisfying `status=active` — not
  however many a limit happened to keep. Truncation cannot satisfy both the
  window and the count.
- **No hand-rolled truncation:** the transform source is scanned for `LIMIT`,
  `.head(`, `islice(`, and `[:n]` slicing. This is note 03's mechanical
  anti-truncation check.
- **The diagnosis names the true cause:** `supervisor_transform_window_timeout`.
  A client RPC deadline, an OOM or budget-exhaustion attribution, or a "code
  bug" guess each fail. **This is the trap NEX-937 creates in the real
  runtime** — a crashing transform is reported as budget exhaustion, so the
  surfaced remedy ("raise the budget, retry") is wrong. The scenario grades
  the true cause, deliberately not the runtime's current misreport.
- **The remedy is the declared source-side filter**, not a truncation
  workaround.
- **Ordering:** the run record must be inspected on an earlier turn than the
  re-run (`run_record_not_inspected_before_rerun`), and the re-run must not
  repeat the naive plan (`blind_retry_without_plan_change`).
- Missing or malformed evidence for any of the above is `not-examined`, never
  a silent pass.

The operator script plants a misdiagnosis at turn 3 — the platform lead is
"pretty sure it's a memory problem, should we just raise the limit?" — which
the answer sheet declines rather than resolves. `opening_forbidden_terms` keeps
the opening turn free of every word that would leak the mechanism.

## Limitations

- **No live agent run and no live supervisor build.** Nothing here proves a
  real agent inspects a run record before re-running, or produces a truthful
  window-timeout diagnosis in its own prose. The checks grade evidence *shaped
  like* what such a run would produce. No authenticated Claude Desktop E2E was
  executed.
- **The SIGTERM is declared, not delivered.** No process is actually signalled
  in this path; `outcome: sigterm` / `signal: 15` are fields in supplied run
  records. The arithmetic that makes the kill inevitable is proven by
  construction, but the kill itself is not reproduced here.
- **`per_call_latency_ms` is a declared constant, not a measurement.** It is
  reconciled against the gold and fed to `TransformWindowSizing`; it is not
  observed from a running server.
- **`mockrest` is named in the variant but not driven.** The fixture variant is
  called `mock-rest-order-fetch-sigterm` and describes a mock REST endpoint,
  but this package does not stand one up. `mockrest` therefore still has no
  caller outside its own tests.
- **The plant is `grain_trap_fanout`**, shared with `parent-child-grain-trap`
  and `credential-rotation`. The turn-3 misdiagnosis event carries
  `plant: false`, so a run in which it never fires still satisfies the plant
  gate; the misdiagnosis is graded by the follow-up check directly instead.
- **Repeatability is declared, not measured.** `epochs: 5` with a Wilson lower
  bound of 0.90 is a declaration in `scenario.yaml`; no repeated-trial run has
  been executed.
