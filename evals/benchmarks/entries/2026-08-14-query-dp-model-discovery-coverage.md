---
id: 2026-08-14-query-dp-model-discovery-coverage
date: 2026-08-14
label: "nxd-query-data-product: describe-every-model discovery + coverage gate (§6d/§6f)"
plugin_version: 0.37.1
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-query-data-product: describe-every-model discovery + coverage gate

## Notes

This PR changes a shipped skill's behavior: §6d step 2 now requires
`describe_model` on every model `list_models` returns (relevance decided from
each response, never before it), and §6f's intent gate gains a step 0
"Coverage — no model skipped". The only public scenario that could distinguish
it is `semantic-intent-validation`, which is `ci_skip`'d — it needs a live
semantic MCP server (the nxd semantic compiler) reaching lower-env Snowflake,
which CI cannot provision. Manufacturing a new scenario arm would measure a
workflow CI cannot run rather than give a trustworthy before/after number, so
this is recorded as `NO_EVAL` with the skip itself as the justification.

## Evidence

`evals/tests/test_semantic_intent_coverage.py` is the carrying test. It asserts
the shipped scenario carries the coverage rule and has teeth: `checks.json` names
the `coverage-all-models-described` check (describe_model on EVERY model), the
fixture catalog contains a decoy model (`partner_directory`) that owns
`partner_sourced_revenue` under a misleadingly reference/lookup-sounding name,
and the prompt no longer teaches the old three-check gate. All three assertions
fail against the pre-fix skill, which described only a self-selected subset of
models.
