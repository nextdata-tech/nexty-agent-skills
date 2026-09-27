---
id: 2026-09-27-self-check-model-aliases
date: 2026-09-27
label: "self-check resolves module-level model-tuple aliases"
plugin_version: 0.54.2
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — self-check resolves module-level model-tuple aliases

## Notes

A live B5 (inventory-position) run authored `API_MODELS = (...)`,
`DERIVED_MODELS = (...)` and `PHYSICAL_MODELS = API_MODELS + DERIVED_MODELS`.
`self_check.py`'s `model_constants` collected only the four canonical names, so
it could not resolve `API_MODELS` and reported
`struct.unverified: transform/main.py: PHYSICAL_MODELS is not a literal`. The
supervisor's trusted read-back has the same reader, which is what actually
failed validation; that half is fixed in nxd.

The reader now also collects every module-level name bound exactly once to a
value (`X = ...` or `X: T = ...`), so a literal tuple or list of strings, a
name alias of one, or a `+` of those resolves. A name that is rebound,
augmented, imported, or bound only inside a branch or function stays
unresolvable, and calls and comprehensions stay `struct.unverified` exactly as
before. `api-source.md` and `self-check.md` now say which forms resolve.

No public scenario can distinguish this: whether an agent writes a helper
alias is authoring style, not something a scenario prompt can require, and the
failure only surfaces behind the supervisor's trusted validation in a live run.

## Evidence

- `evals/tests/test_self_check_queryability_and_phase_gates.py` —
  `test_b5_shaped_module_alias_resolves` and
  `test_annotated_and_chained_aliases_resolve` fail against the previous
  `self_check.py`; `test_computed_model_constants_stay_unverified` pins calls,
  comprehensions, imported, rebound and branch-bound names as still
  unverified.
