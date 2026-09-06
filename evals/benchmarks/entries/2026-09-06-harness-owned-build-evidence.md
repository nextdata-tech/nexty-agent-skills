---
id: 2026-09-06-harness-owned-build-evidence
date: 2026-09-06
label: "read build evidence from the runner's own data directory"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — read build evidence from the runner's own data directory

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

## Evidence

- `evals/dp-scenarios/tests/test_runner_claude_adapter.py` — build facts come
  from the runner's own copy of the release; a release for a run this session
  did not build is still refused; the highest published release wins on disk
  too; a missing or unreadable state directory contributes nothing; and a
  lifecycle observed on an earlier turn is not published beside a later run's
  identifiers.
