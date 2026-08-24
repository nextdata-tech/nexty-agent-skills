---
id: 2026-08-24-phase-a-connector-aware-data-dirs
date: 2026-08-24
label: "Phase A's data/ comparison respects the connector type instead of firing on every api-source closure"
plugin_version: 0.38.3
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — Phase A's data/ comparison respects the connector type

## Notes

No eval arm can say anything true about this. The public scenarios that reach a
self-check either build a csv-source closure, where the rule is unchanged, or
never land reference data on a network connector at all, so a before/after pair
would compare two runs that behave identically. The one closure shape that
distinguishes the change — an api-source closure that lands `nxd_decisions` —
has no scenario, and manufacturing one to produce a number would measure the new
fixture rather than the pack. The carrying tests are the evidence instead.

**What was wrong.** Phase A compared `BASE_MODELS` against the `data/`
directories and demanded equality whenever `data/` existed. Equality is the
right invariant only when every base model is *exported* to `data/`, which is
true of a csv-source or file-source closure and false of an api-source or
db-source one: those base models are fetched over the network at transform time
and correctly have no directory.

Such a closure may still carry `data/` for reference data it authored itself,
and `nxd-generate-data-product/reference/api-source.md` § "Landed reference data
in an API closure" is where the author is told to write it. The pack also
requires every ruling to land as data, so any closure recording one carries
`data/nxd_decisions/`. The two rules together mean equality fired on **every
correct api-source closure that records a ruling** — which is close to all of
them. A gate that fires on every correct closure gets worked around rather than
obeyed, which is the same reasoning Phase E's transport waiver is built on, two
hundred lines further down the same file.

The disagreement was visible from outside: on the same closure,
`check_data_product` returned `pass` on all four stages while `self_check.py`
returned `fail`. An agent cannot use an offline gate it has been taught to
disbelieve, and the obvious way to satisfy it is to damage the closure.

**What changed.** The comparison is now connector-aware. `declared_connectors()`
already existed for Phase E — AST string-literal reads, labelled instances
matched by prefix — and is now evaluated once above Phase A so both gates read
one declaration rather than two parsers drifting apart. For a closure declaring
`api-source` or `db-source` the invariant is **containment**: a `data/`
directory naming no base model is still a finding, because it lands nothing,
while a base model with no directory is normal. Everything else keeps equality.

An unreadable declaration takes the containment branch, matching the reason
Phase E already gives for its own waiver: a declaration this gate could not read
is not evidence of a non-network closure. A mixed closure declaring both
families takes it too, because some of its base models really are fetched.

**Scope.** Phase A only. No change to what the supervisor pins, to Phase B, C, D,
E or G, or to any generated closure.

## Evidence

- `evals/tests/test_base_models_data_dirs_gate.py` — 7 tests over synthetic
  closures run through the shipped `self_check.py`: the api-source closure that
  lands reference data is clean; labelled `api-source-github` and
  `db-source-orders` are recognised as the same kinds; a `data/` directory
  naming no base model still fires; csv-source and file-source keep equality
  and still fire on a missing directory; an exactly-matching csv-source closure
  stays clean. Verified to fail against the previous implementation: **3 of the
  7 fail** with `src/nxd-run-job-loop/scripts/self_check.py` restored to its
  pre-change state — the three false-positive cases. The other four pass before
  and after, which is the point: they pin behaviour the change must not alter.
- Confirmed on a real closure rather than only on fixtures. The api-source
  closure at `nxd-jobs/linear-pocket-priorities-portable/closure` (13 promised
  models, GraphQL source, `data/` carrying `nxd_decisions`, `scoring_rubric`,
  `verdict_thresholds`, `mapper_reviews`) reported
  `struct.base_models_vs_data_dirs` before and reports it no longer. Its one
  remaining error is `grant.spec_unreadable`, which is a true finding: the
  mapper spec's thresholds are unfilled.
- `python3 scripts/validate_skills.py --root .` — passes.
- `./build-skills.sh` — packages, 200-entry cap respected on every skill.
- `python3 evals/benchmark_record.py --check` — entries and index valid.
