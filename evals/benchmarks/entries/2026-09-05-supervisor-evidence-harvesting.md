---
id: 2026-09-05-supervisor-evidence-harvesting
date: 2026-09-05
label: "read the supervisor's real query and release payloads"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — read the supervisor's real query and release payloads

## Notes

Harness-only: `_update_machine_artifacts` in the live Claude adapter. No skill
under `src/` changes, no scenario, answer sheet or prompt changes. A public
scenario arm would drive the same skills against the same fixtures either way,
so no runnable arm can distinguish it.

The change was found by a live `crm-pipeline` run on 2026-09-05 that completed
all eleven turns and still graded `build` and `query` as **not examined**. The
agent had not failed. It paginated the source, published release 6, and ran six
semantic queries that returned correct rows. The harness could not read either
answer:

1. **Positional query rows.** The supervisor returns `rows` as a list of lists
   beside a `columns` header. The harvester required `all(isinstance(row,
   Mapping))`, so it discarded every row of every query and never wrote
   `query-results.json`. `query_actual_not_examined` was therefore unreachable
   to fix by any agent behaviour.
2. **Build facts read from the wrong tool.** `publish_seq` and the per-model row
   counts were harvested only from `list_data_products`, which answered
   `{"products": []}` on the live run *while release 6 existed*. The verified
   release resource — the payload the supervisor itself labels
   `trust: artifact_verified` — carries the published `run_id`, `artifact_id`,
   `publish_seq` and `evidence.model_tables[].row_count` together, and is now
   the source. `list_data_products` stays as a fallback for the replay fixtures.

Attribution is preserved and tightened rather than relaxed. Facts are accepted
only for a run this session actually built: the harvester tracks the set of
successful `build_data_product` run ids, and a verified release naming any
other run is refused outright. That matters because a leftover release from an
abandoned job would otherwise be able to hand the build gate identifiers and
row counts the agent never produced. Where several releases are read, the
highest `publish_seq` wins, because an earlier one is a superseded attempt.

Replaying the captured live observations through the fixed harvester now
produces both artifacts, with `publish_sequence: 6` and row counts
`{main.deals: 6, main.deals_raw: 6, main.nxd_decisions: 2}` — the numbers the
supervisor published.

This does not make the scenario pass, and no attempt was made to make it do so.
The same run shows the agent never ran a query returning the gold column set
(`deal_id`, `stage`, `amount`, `updated_at`), so the query gate should now fail
on merit instead of reading not-examined. Turning a false "not examined" into a
true failure is the point of the change.

## Evidence

- `evals/dp-scenarios/tests/test_runner_claude_adapter.py` — seven tests over
  the shapes captured from the live run: positional rows are read through their
  column header, mapping rows still work, a row that does not fit its header is
  dropped rather than zipped short, supervisor facts come from the verified
  release, a release from a run this session never built is refused, the highest
  publish sequence wins, and an errored resource read contributes nothing. The
  first and fourth fail against the previous implementation.
