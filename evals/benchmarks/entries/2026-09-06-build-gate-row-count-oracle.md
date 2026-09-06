---
id: 2026-09-06-build-gate-row-count-oracle
date: 2026-09-06
label: "drop a build row-count comparison whose two sides were never the same thing"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — drop a build row-count comparison whose two sides were never the same thing

## Notes

Harness grading only; no skill under `src/` changes and nothing agent-visible
moves, so no runnable public arm can distinguish it.

**How it surfaced.** A live `crm-pipeline` run graded `build=FAIL` with six
`build_row_count_mismatch` findings. The supervisor side, harness-owned since
`227d03bd`, read `{"main.active_deals": "5", "main.deals_raw": "6",
"main.pages_log": "3", ...}` — built model names, schema-qualified, stringified.
The oracle side (`runner/tier.py`) was `synthgen`'s `table_row_counts`, which
for that scenario is `{"deals": 1}` — a source table name with an integer value,
and in fact a fixture-identity placeholder: the CSV holds one row
(`FIXTURE-29-001`) and the manifest says the graded rows come from the mock
source. Nothing an agent could have built would have passed.

**It was not a route-backed quirk.** The first reading was that route-backed
scenarios needed a waiver. They do not: a file-backed scenario compares
`{"main.orders": "12"}` against `{"orders": 12, "order_lines": 40}` and fails
for the identical reason. The comparison has never passed on a live run for any
scenario. The replay tests passed only because they seed the supervisor side
*from* `generated.manifest["table_row_counts"]` — evidence derived from the
oracle, so the assertion was self-fulfilling and no test ever exercised the
live shape.

**It is not repairable by normalising.** There is no source row count that
survives modelling. `parent-child-grain-trap` exists precisely because the built
model must *not* preserve the child grain, and the live run's `pages_log` and
`transport_log` models have no source table behind them at all. Deriving an
expectation from the mock counters instead was rejected too: the counters record
requests, methods and pages, never records served, and any number derived from
the route config would still be a rule about how many models the agent should
build and what to name them — which no scenario declares.

**What changed.** `gate_build` keeps the three
`build_supervisor_identifier_missing` checks and drops the count comparison,
`build_row_count_mismatch`, `build_row_counts_not_examined` and the now-dead
`_counts` helper. `examined` becomes `bool(supervisor)`: the harness read facts
or it did not. Keying it off the counts would have made an absent release
*not-examined* rather than failing, which is the dodge this file keeps closing.

Deliberately **not** a waiver. `build` stays `required=True` and stays in
`_pass_rule` unconditionally, so requiredness is still a property of the
scenario declaration and an agent that builds nothing still fails the gate: no
release means no supervisor identifiers means three findings. A not-staged code
would also have listed `build` under `waived_gates` while it still carries 20
required points, which would misreport the threshold.

Count honesty is not lost. `ledger/lint.py` compares every ledger-claimed
`per_model_row_counts.<model>` against the supervisor's value and flags any
model the agent left unrecorded — the check that actually catches a false claim
about counts, and the one this gate was never doing.

The gate's remaining claim is thinner than the README implied, so
`evals/dp-scenarios/README.md` and
`scenarios/parent-child-grain-trap/README.md` now say what it checks rather
than leaving a reader to infer a comparison that no longer exists.

**What `CERTIFIED` now means.** Eight of the nine scenarios declare
`repeatability.certification.gates: [build]`; only `parent-child-grain-trap`
adds `query`. `repeatability_certificate` certifies an epoch when
`_gate_observation(run, "build") == (True, True)`, so after this change a
certificate attests that each epoch published a release the harness could
identify — not what was built, nor that it was stable epoch to epoch. Nothing
regresses in practice, since the comparison this commit removes could never
pass live and those certificates were therefore unreachable; but `CERTIFIED` is
a user-facing disposition and it is now a thinner claim. Putting substance back
means adding a content-bearing gate to `certification.gates` where the scenario
has one, which is a scenario-semantics change and is deliberately not made
here.

## Evidence

- `evals/dp-scenarios/tests/test_grading_gates.py` — the live shape
  (`{"main.active_deals": "5", ...}` against `{"deals": 1}`) now passes, and the
  oracle is ignored whatever it says; a missing identifier and absent facts both
  still fail, with absent facts reading not-examined. The first of those fails
  against the previous implementation.
- `evals/dp-scenarios/tests/test_runner_tier.py` —
  `test_tier_build_gate_failure_cannot_produce_a_clean_verdict` keeps its claim
  with a new lever: one epoch with no published release, since
  `SupervisorFacts` rejects a null identifier at replay load and a corrupted
  count is no longer read.
