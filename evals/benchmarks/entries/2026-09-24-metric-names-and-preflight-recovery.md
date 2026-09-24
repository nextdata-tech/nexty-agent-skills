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
`check_data_product`. A live B1 run on the same day also failed validation.
It had followed our guidance to import `DurationUnit` from
`nxd.core.yaml_schemas`, but supervisor validation allows only `nxd.spec.*`
imports in `models.py`. The guidance now imports from `nxd.spec.data_types`.
A later B3 run still churned. Each review round raised a new MEDIUM finding,
"the verifier would not catch a hypothetical future bug", while it confirmed
the current output was correct. The job loop blocks on MEDIUM. The reviewer now
grades verification gaps by what they hide today: HIGH if an output is wrong
now, MEDIUM if the blueprint promises that check, and LOW (advisory) otherwise.
With those fixes, B3 published and passed intake, build and follow-up. It
scored 35 against a threshold of 36. The only construction finding was
`construction_adversarial_review_unresolved`: an earlier `needs_user` review
round kept `user_decision: null` after the operator authorized its corrections.
`workflow-v2.md` now says to close that round before resetting. The next run
confirmed every fix and was left with one LOW advisory claim, yet the agent
still held publication. The supervisor is satisfied only by a clear report
with no findings, and nothing said that an advisory-only round resolves to
clear. `workflow-v2.md` now says so, while the claim stays in the ledger.

No public `evals/run.py` scenario isolates this. The trigger depends on how
many aggregate-only views an agent authors. The B3 live rerun is the
qualification check. Deterministic evidence pins the guidance.

## Evidence

- `evals/tests/test_source_contract.py` —
  `test_metric_names_are_registry_unique_and_check_runs_before_capture` pins
  the example, the global-name rule, the required pre-capture check, and the
  recovery section; it fails against the previous skill files.
- `evals/tests/test_source_contract.py` — `test_models_imports_stay_inside_nxd_spec`
  pins the `nxd.spec.data_types` import; it fails against the previous files.
- `evals/tests/test_source_contract.py` —
  `test_review_grades_verification_gaps_by_what_they_hide_today` pins the
  severity calibration; it fails against the previous review skill.
- `evals/tests/test_source_contract.py` —
  `test_pending_review_round_is_closed_before_reset` pins the close-before-reset
  step; it fails against the previous `workflow-v2.md`.
- `evals/tests/test_source_contract.py` —
  `test_advisory_only_review_rounds_report_clear` pins the advisory-only
  resolution; it fails against the previous `workflow-v2.md`.
