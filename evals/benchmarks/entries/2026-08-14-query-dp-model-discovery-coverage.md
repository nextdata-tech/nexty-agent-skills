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
on two sides.

**Over the shipped skill — verified to fail against the previous
implementation.** Three assertions read
`src/nxd-query-data-product/SKILL.md` directly: that §6d step 2 requires
`describe_model` on EVERY model and forbids deciding relevance first, that §6f's
gate says "Run all four" and opens with "Coverage — no model skipped" declaring
a differing grain an invalid skip, and that §6f step 0 scopes coverage to the
*agreed scope* so it does not contradict the large-catalog narrowing §6d
permits. Restoring `SKILL.md` from `origin/main` and touching nothing under
`evals/` turns exactly these three red (verified: 3 failed, 5 passed), so a
revert of the instruction cannot ship green.

**Over the eval arm — guards the scenario from drifting back.** `checks.json`
names the `coverage-all-models-described` check, the fixture catalog carries the
`partner_directory` decoy owning `partner_sourced_revenue` behind a
lookup-table-sounding name, and — graded through the runner's own
`agent_task_from_prompt` — the agent-facing task section names neither the
coverage rule nor the decoy's metric. That last one matters for attribution: the
task section is handed to the agent verbatim, so restating the graded checks
there would let a `no_skills` baseline pass them and the arm would measure
prompt-following instead of the skill.
