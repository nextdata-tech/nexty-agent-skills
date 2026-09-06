---
id: 2026-09-06-harness-owned-build-evidence
date: 2026-09-06
label: "own the build evidence, and stop comparing source tables with built models"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — own the build evidence, and stop comparing source tables with built models

## Notes

Harness-only. No skill under `src/` changes, no scenario or prompt changes, so
no runnable public arm can distinguish it.

`build` is required for every scenario, and whether it could be examined
depended on which MCP tools the agent happened to call. `publish_seq` and the
per-model row counts were harvested only from `list_data_products` (which
answered `{"products": []}` on a live run while the release existed) and then,
after an earlier fix, from `read_data_product_resource`. Two otherwise
identical live `crm-pipeline` runs differed only in whether the agent
volunteered that resource read — one had its build examined, the other did not.
An agent that built correctly and published a release was failed on a required
gate for not producing evidence nobody asked it for. That is the mirror image
of the dodge risk the requiredness work guards against: not an agent evading a
gate, but a good agent being failed by one.

The supervisor already writes the evidence to disk. Under its data directory,
`workflows/*/releases/release-*.json` carries `run_id`, `artifact_id`,
`publish_seq` and `verification.row_counts` — already the exact
`per_model_row_counts` shape. That directory is a runner-owned temporary path
and the agent has no shell, so nothing in it is agent-influenced. The adapter
now reads it after each turn and fills the facts from there, with the relayed
MCP payloads kept as the earlier, weaker source.

The shape was confirmed against a real supervisor, and separately the *wiring*
was not -- the first version of this change set `_state_dir` only when the
adapter started its own server, while the live runner passes `--mcp-config` and
starts the supervisor itself. The reader was therefore inert on every
production run while every unit test that called it directly passed. Review
caught it; the adapter now receives `--supervisor-data-dir` from the
environment that started the supervisor, and a test asserts the argument
reaches the attribute the reader is gated on. Confirming a parser is not
confirming a feature.

The record shape, for its part, was confirmed rather than assumed: a local
`drift-canary` build produced

    "publish_seq":"1", "run_id":"run-2c1b7440-…", "artifact_id":"artifact-09a2277d-…",
    "verification":{"outcome":"passed","row_counts":{"main.orders":"2", …}}

and replaying that directory through the new reader yields the complete fact
set. Guessing the payload shape is what caused the `list_data_products` defect
in the first place; the `nxd-desktop-supervisor status` CLI was tried first and
rejected because it reports only `current_artifact` and `pointer`.

`lifecycle_state` is `terminal` when a release record exists. A record is
written only for a run that finished and published, and `terminal` is what the
supervisor reports for such a run through `inspect_run`, so the harness-owned
value agrees with what a correct agent would claim.

Attribution is unchanged and still the load-bearing rule: only a release naming
a run this session built is accepted, so a leftover release from an abandoned
job cannot supply identifiers the agent never produced. Highest publish
sequence wins.

### What owning it exposed: a comparison whose sides were never the same thing

Wiring the reader for real made the next live `crm-pipeline` run grade
`build=FAIL` with six `build_row_count_mismatch` findings. The supervisor side
read `{"main.active_deals": "5", "main.deals_raw": "6", "main.pages_log": "3",
...}` — built model names, schema-qualified, stringified. The oracle side was
`synthgen`'s `table_row_counts`, which for that scenario is `{"deals": 1}` — a
source table name with an integer value, and in fact a fixture-identity
placeholder: the CSV holds one row (`FIXTURE-29-001`) and the manifest says the
graded rows come from the mock source. Nothing an agent could build would have
passed.

It was not a route-backed quirk. A file-backed scenario compares
`{"main.orders": "12"}` against `{"orders": 12, "order_lines": 40}` and fails
identically; the comparison had never passed on a live run for any scenario. The
replay tests passed only because they seed the supervisor side *from*
`generated.manifest["table_row_counts"]` — evidence derived from the oracle, so
the assertion was self-fulfilling and no test exercised the live shape.

Nor is it repairable by normalising names and types. No source row count
survives modelling: `parent-child-grain-trap` exists precisely because the built
model must *not* preserve the child grain, and the live run's `pages_log` and
`transport_log` models have no source table behind them at all. Deriving an
expectation from the mock counters was rejected too — they record requests,
methods and pages, never records served, and anything from the route config
would be a rule about how many models the agent should build and what to name
them, which no scenario declares.

So the comparison is gone. `gate_build` keeps the three
`build_supervisor_identifier_missing` checks and drops
`build_row_count_mismatch`, `build_row_counts_not_examined` and the dead
`_counts` helper. `examined` becomes `bool(supervisor)`: keying it off the
counts would make an *absent release* read not-examined rather than failing.

Deliberately **not** a waiver. `build` stays `required=True` and stays in
`_pass_rule` unconditionally, so an agent that builds nothing still fails it. A
not-staged code would also have listed `build` under `waived_gates` while it
still carries 20 required points. An identifier is absent when it is `None` or a
blank string — not merely falsy, since `claude_adapter` accepts an integer
`publish_sequence`.

Count honesty is not lost: `ledger/lint.py` compares every ledger-claimed
`per_model_row_counts.<model>` against the supervisor's value and flags any
model the agent left unrecorded. That is the check that actually catches a false
count claim, and the one this gate was never doing.

**What `CERTIFIED` now means.** Eight of the nine scenarios declare
`repeatability.certification.gates: [build]`; only `parent-child-grain-trap`
adds `query`. A certificate therefore attests that each epoch published a
release the harness could identify — not what was built, nor that it was stable
epoch to epoch. Nothing regresses in practice, since the comparison removed here
could never pass live and those certificates were unreachable; but `CERTIFIED`
is user-facing and it is now a thinner claim. Putting substance back means
adding a content-bearing gate to `certification.gates`, a scenario-semantics
change deliberately not made here.

## Evidence

- `evals/dp-scenarios/tests/test_runner_claude_adapter.py` — build facts come
  from the runner's own copy of the release; a release for a run this session
  did not build is still refused; the highest published release wins on disk
  too; a missing or unreadable state directory contributes nothing; and a
  lifecycle observed on an earlier turn is not published beside a later run's
  identifiers.
- `evals/dp-scenarios/tests/test_grading_gates.py` — the live row-count shape
  now passes and the oracle is ignored whatever it says; a missing or blank
  identifier fails while an integer `0` sequence does not; absent facts read
  not-examined.
- `evals/dp-scenarios/tests/test_runner_tier.py` — one epoch whose release
  carries no identity sinks the tier, with honesty clean and every other
  required gate passing, so the lever isolates `build`.
  The first two fail against the previous implementation.
