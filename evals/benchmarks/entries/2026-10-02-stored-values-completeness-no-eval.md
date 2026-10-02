---
id: 2026-10-02-stored-values-completeness-no-eval
date: 2026-10-02
label: "nxd-query-data-product: use values_complete / values_omitted from describe_model to decide whether to probe stored values"
plugin_version: 0.54.15
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-query-data-product: use values_complete / values_omitted from describe_model to decide whether to probe stored values

## Notes

The query skill (and the nxd_eval agent prompt preamble) now tells the agent how
to read the stored-values fields that nxd PR #8141 adds to `describe_model`:
`values_complete: true` means the list is exhaustive, so an absent value is
reported as a mismatch with no probe; `values_complete: false` means the list is
encoding examples only, so the existing probe still runs; `values_omitted` set
or no `values` field means probe as before; PII dimensions are never enumerated.

No live scenario can distinguish this change. The `values`, `values_complete`
and `values_omitted` fields do not exist on any served data product until #8141
is deployed, so every arm, before or after, sees a `describe_model` response
without them and takes the unchanged "no values field" path. A paired run today
would measure run-to-run variance, not this change. Manufacturing a fixture that
fakes the fields would grade the fixture, not the product. This pairs with nxd
#8141 and should merge after it deploys; a measured pair becomes possible then.

## Evidence

- `evals/nxd_eval/tests/test_skill_prompts.py` — the carrying test.
  `test_prompt_carries_the_stored_values_completeness_rule` asserts the rendered
  agent prompt carries both the preamble rule and the skill-sourced guidance for
  `values_complete` true and false, `values_omitted`, and the PII rule. It fails
  against the previous prompt, which has none of that text.
- `python3 scripts/validate_skills.py --root .` and `./build-skills.sh` pass.
- Version lockstep holds at 0.54.15 across `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, and every `src/*/SKILL.md`.
