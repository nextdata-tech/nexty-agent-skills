# When questions require inference

How the loop handles a question that needs a **judgement produced by reading
each entity's evidence** — a per-entity score, verdict, or classification the
source does not state. The landed *shape* (row schema, evidence citation, batch
convention) is owned by nxd-generate-data-product's `reference/llm-judgments.md`; this file
owns *when the agent judges* inside the loop.

## Contents

- [The rule: land judgement as data, agent-side](#the-rule-land-judgement-as-data-agent-side)
- [Teach before you judge](#teach-before-you-judge)
- [Judge agent-side, never in a query answer](#judge-agent-side-never-in-a-query-answer)
- [Judge incrementally](#judge-incrementally)

## The rule: land judgement as data, agent-side

Some questions need a judgement produced by reading each entity's evidence —
score candidates against a rubric, assign tickets a verdict, classify rows on a
dimension the data doesn't carry. That is real analytical value, but it is
nondeterministic, so it must not live in the deterministic build. Route it the
same way you route any ruling: **land it as data, produced agent-side, before the
build.** nxd-generate-data-product's `reference/llm-judgments.md` has the row schema.

## Teach before you judge

A judgement is only checkable against a rubric that already exists as data. A
score of "4" means nothing until "out of the landed 1–5" is landed. Elicit or
confirm the rubric — criteria, weights, scale, verdict enum, gates — and have
nxd-generate-data-product land it (and an `nxd_decisions` row, classified
`provenance = user_confirmed` where the user supplied the rubric and
`agent_authored` for any anchor or band you filled in yourself) FIRST,
before any entity is judged.

## Judge agent-side, never in a query answer

Read the entity facts and write the judgement rows as CSV — `status = proposed`,
each row carrying a verbatim evidence citation (`evidence_field` +
`evidence_quote`, or `not stated`). Never score in a `run_semantic_query` answer,
a scratch table, or a transform constant — all the same fabrication the loop
exists to prevent. The build only consumes the landed rows; it never invokes a
model.

## Judge incrementally

For a re-run or a handoff, do not re-score the whole population. Score only
`source keys − already-judged keys` (for the current `rubric_version`), append
those rows as a **new** `batch-00N.csv` (never edit an existing batch — dlt
replace-loads every batch each build, so a new file is a legitimate input change,
not drift), and rebuild through MCP with the **same** `workflow` id.

A rubric change is a new `rubric_version`, landed explicitly — never an in-place
edit that silently invalidates existing judgements. If no live agent is available
to judge new entities on an unattended rerun, the product degrades honestly:
unjudged entities land in an explicit unscored bucket and are reported, never
faked.
