---
id: 2026-08-06-desktop-contract-gate-claim-corrected
date: 2026-08-06
label: "nxd-generate-data-product: retract the \"only durable data-quality gate\" claim"
plugin_version: 0.36.3
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-generate-data-product: retract the "only durable data-quality gate" claim

## Notes

No scenario arm can distinguish this change, because nothing about closure
authoring changed. `SKILL.md` Step 3b previously asserted that the mandatory
in-transform asserts are "the ONLY durable data-quality gate on desktop", on the
stated grounds that "the local driver's verify is a no-op and platform-side
contract verification doesn't run locally". The desktop runtime has executed
user-authored contracts since 2026-07-31: custom input expectations run before
the transform, and custom output promises run after the DuckDB writes and block
publication when violated. The sentence was a stale factual claim about the
runtime, not an instruction.

The edit retracts that claim and states the true relationship — the asserts are
the in-transform gate and remain mandatory, contracts are enforced by the
runtime, and neither substitutes for the other, since a promise cannot observe
the intermediate state an assert checks. **No requirement was added, removed, or
loosened**: a closure authored before this change and one authored after are
identical, so any measured arm would differ only by agent nondeterminism.
Manufacturing a scenario to produce a number here would make the evidence less
trustworthy, not more.

The accompanying scenario-count corrections in `evals/README.md`,
`evals/GETTING-STARTED.md`, and `evals/affected_scenarios.py` are harness-doc
text that no scenario reads.

Review of this change found the retracted claim had also survived verbatim in
the `derived-model-asserts` check of `generate-runnable-dp-from-intent` — judge
text, not skill text, and so outside this entry's scope. That edit *was*
verified by a run, recorded separately in
[`2026-08-06-desktop-gate-claim-rubric-verified`](2026-08-06-desktop-gate-claim-rubric-verified.md).
The two entries together cover the change: `NO_EVAL` for the skill prose, a
measured PASS for the rubric.

## Evidence

`evals/tests/test_desktop_custom_contract_checker.py` is the carrying test: it
exercises the public custom-contract checker against valid and broken closures —
sync and async verifier acceptance, duplicate-name detection, decorative-script
rejection, and literal-secret gating. Its existence is what makes the retracted
claim demonstrably false: the pack already generates and gates executable
custom contracts for the desktop path, and the `desktop-custom-contracts`
public scenario covers the generated form end to end.
