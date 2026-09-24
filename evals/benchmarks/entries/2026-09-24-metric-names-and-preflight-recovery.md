---
id: 2026-09-24-metric-names-and-preflight-recovery
date: 2026-09-24
label: "registry-unique metric names, required pre-capture check, validation-failure recovery"
plugin_version: 0.52.6
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — registry-unique metric names, required pre-capture check, validation-failure recovery

## Notes

A live B3 `marketing-attribution` Sonnet run on 2026-09-24 converged its review
in two rounds. Supervisor validation then failed twice with only
`validation/preflight_failed`. Running the retained capture through the
supervisor's spec compiler showed the real cause: a duplicate metric name
`row_count` across three semantic views. The generator's own example produced
it. The agent had not called `check_data_product`, because the job loop called
self-check optional. So it audited the closure by hand and stopped.

The skills now use `<model>_row_count` and state that metric names are
registry-global. They require the shellless `check_data_product` MCP tool
before every capture, including after a repair. `workflow-v2.md` now has a
"When validation fails" recovery keyed on the supervisor's `recovery`
disposition. The dp-scenarios conduct line no longer reads as forbidding
`check_data_product`.

No public `evals/run.py` scenario isolates this. The trigger depends on how
many aggregate-only views an agent authors. The B3 live rerun is the
qualification check. Deterministic evidence pins the guidance.

## Evidence

- `evals/tests/test_source_contract.py` —
  `test_metric_names_are_registry_unique_and_check_runs_before_capture` pins
  the example, the global-name rule, the required pre-capture check, and the
  recovery section; it fails against the previous skill files.
