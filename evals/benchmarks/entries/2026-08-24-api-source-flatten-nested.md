---
id: 2026-08-24-api-source-flatten-nested
date: 2026-08-24
label: "api-source closures flatten nested GraphQL selections before the port"
plugin_version: 0.38.5
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nested GraphQL selections are flattened before the port

## Notes

No eval arm distinguishes this. Every public scenario that reaches an
`api-source` closure either fetches flat scalars or never lands a nested
selection, so a before/after pair would compare two runs that behave
identically. The shape that separates them — a query selecting a nested object
and a nested list — has no scenario, and building one would measure the new
fixture rather than the pack. The carrying tests are the evidence.

**What was wrong.** dlt restructures nested JSON two different ways, and only one
is caught:

- a nested **list** becomes a child table (`labels.nodes` →
  `linear_issues_landed__labels__nodes`), which appears in
  `data_table_names()` and trips the mandatory read-back assert. Loud, correct.
- a nested **dict** becomes `__`-joined columns (`state` → `state__name`,
  `state__type`). No extra table, so the read-back assert **cannot see it**. A
  `models.py` declaring the obvious `state_name` binds to a column that does not
  exist: the product builds, publishes and serves with that dimension empty.

The second is the same silent class as a `primary_key()` carrying no
`dimension()` — no error, no failed assert, no missing table, only questions
that quietly have no answer.

Nothing in the pack covered either. `add_map` appeared in no file;
`parent__field` appeared only in the derived-model context, describing dicts a
`@dlt.resource` yields rather than rows arriving from an API; and the worked
GraphQL query selected only flat scalars, so the example was the one shape that
could not hit it.

**What changed.** `api-source.md` gains a section naming both modes with the
observed table and column output, a `_flatten_issue` helper, and the `.add_map()`
placement ahead of `.with_name(...)`. The reader loop in the transform diff shows
the same shape. The worked query now selects `state { name type }`,
`assignee { name }` and `labels { nodes { name } }`, so the example produces
every column the evidence block prints — an earlier revision printed
`assignee__name` from a query that never selected it, which made the block
unreproducible from the doc's own example.

**Scope.** Documentation and its pinning tests. No code path changes, and no
generated closure changes except through an author following the recipe.

## Evidence

- `evals/tests/test_api_source_graphql_body_contract.py::test_recipe_teaches_flattening_of_nested_selections`
  — doc contract: pins `add_map`, the `state__name` shape, both failure modes
  distinguished, and the nested worked query.
- `…::test_pinned_dlt_really_splits_nested_lists_and_flattens_nested_dicts` — a
  live probe in the file's existing Layer-2 style, running the pinned
  `dlt==1.28.2` over a payload matching the doc's query and asserting the child
  table appears, `state__name` / `state__type` / `assignee__name` appear, and
  `state_name` does not. If a future dlt changes either behaviour the guidance is
  wrong and this fails rather than the doc rotting. Checked non-vacuous by
  breaking the expected table name.
- `uv run … pytest evals/tests/test_api_source_graphql_body_contract.py -q` — 14
  passed.
- `python3 scripts/validate_skills.py --root .` — passes.
- `./build-skills.sh` — packages, 200-entry cap respected on every skill.
- `python3 evals/benchmark_record.py --check` — entries and index valid.
