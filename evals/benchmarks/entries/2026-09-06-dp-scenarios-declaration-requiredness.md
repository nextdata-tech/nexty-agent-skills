---
id: 2026-09-06-dp-scenarios-declaration-requiredness
date: 2026-09-06
label: "dp-scenarios declaration-based gate requiredness and waived coverage"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — dp-scenarios declaration-based gate requiredness and waived coverage

## Notes

No public eval arm can distinguish this harness-only change. The change is in
scenario declaration loading, deterministic gate wiring, score/report
serialization, and qualification metadata; it does not change a shipped skill
or an agent-facing scenario behavior. Creating a new arm would manufacture a
number rather than measure a skill change. The relevant behavior is covered by
deterministic unit and loader tests instead.

## Evidence

- `evals/dp-scenarios/tests/test_scenario_loader.py` — per-scenario required-set
  assertions, the public gate coverage floor, and the definition-change
  declaration seam.
- `evals/dp-scenarios/tests/test_grading_gates.py` — distinct not-staged codes
  and the staged missing-evidence anti-dodge guarantee.
- `evals/dp-scenarios/tests/test_grading_score.py` — waived scoreable maximum
  and threshold calculations.
- `evals/dp-scenarios/tests/test_runner_report.py` and
  `evals/dp-scenarios/tests/test_runner_qualification_reasons.py` — visible
  waived coverage in reports and CERTIFIED/QUALIFIED reasons.
