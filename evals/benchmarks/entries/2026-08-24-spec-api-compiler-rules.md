---
id: 2026-08-24-spec-api-compiler-rules
date: 2026-08-24
label: "nxd-spec-api.md documents registry-wide dimension names and join-covers-grain"
plugin_version: 0.38.4
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — two compiler rules reach the file authors are told to trust

## Notes

No eval arm distinguishes this. Both rules are enforced by the spec compiler, so
a closure that violates either never reaches a scored run — it fails at
`structure/spec_compile_failed` before any question is asked. An arm would
compare a run that answers questions against a run that never starts, which
measures the fixture rather than the pack. Manufacturing that number would make
the ledger less trustworthy, so this entry carries the evidence instead.

**What was wrong.** `nxd-spec-api.md` is the file authors are explicitly told to
trust over re-reading source — *"Trust this file. Do not re-verify these
signatures…"* — and it omitted two rules the compiler enforces:

- `dimension(name=...)` is unique across the **join-connected registry**, not per
  model. Two models a `join()` relates may not both declare `created_at`.
- `join(to_column=...)` must cover the target model's `primary_key()`, not merely
  a column whose values look unique.

Neither is visible offline: `self_check.py`'s structural phase parses `models.py`
against the surface this file describes and passes on both. They surface only
from `check_data_product`, one build round-trip each.

**Scope, pinned by probe rather than assumed.** The uniqueness rule fires only
once a join connects the models. Two models each declaring `created_at` with no
join between them compile clean, and still compile clean with a `semantic_view`
added; the same pair plus a join fails. The doc says "join-connected registry"
for that reason — an earlier draft of the issue overstated it as any two models,
and #197 carries the correction.

**What deliberately did not change.** The file's `v0.41.139` version pin is left
alone. Only these two rules were reproduced against the installed 0.41.172, not
the whole surface, and the "Version pin and drift" section now says exactly that
rather than implying a full re-verification.

**Placement.** The offline-blind-spot note sits after the last role-builder
bullet, not between two of them: a blank line plus an unindented paragraph ends a
CommonMark list, which split the six role builders into two lists and made the
note read as an introduction to the ones below it. That is the convention the
file already uses for section-level notes.

## Evidence

- `evals/tests/test_spec_api_compiler_rules.py` — 5 tests pinning both rules,
  their quoted compiler errors, the tag-every-dimension guidance with its worked
  collision case, the offline blind spot, and the list placement. Verified to
  fail against the previous implementation: **all 5 fail** with
  `src/nxd-generate-data-product/reference/nxd-spec-api.md` restored to its
  `origin/main` state.
- Both errors reproduced against the shipped compiler at `nxd` 0.41.172
  (`~/.nxd/desktop-venv/bin/python ~/.nxd/bin/py/spec_compile.py <closure> <out>`),
  exit 1 each. The compiler prints `deployment-spec.yaml: OK` *after* the error
  line and still exits non-zero, which the doc now records — the tail of a
  failing run reads as success.
- `python3 scripts/validate_skills.py --root .` — passes.
- `./build-skills.sh` — packages, 200-entry cap respected on every skill.
- `python3 evals/benchmark_record.py --check` — entries and index valid.
