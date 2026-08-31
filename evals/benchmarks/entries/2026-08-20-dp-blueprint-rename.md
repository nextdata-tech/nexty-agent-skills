---
id: 2026-08-20-dp-blueprint-rename
date: 2026-08-20
label: "the user-owned IR is named dp-blueprint.md; the whole artifact family follows"
plugin_version: 0.38.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — the user-owned IR is named dp-blueprint.md; the whole artifact family follows

## Notes

A rename, and no eval arm can say anything true about it. The scenarios that
touch this artifact assert its path — `checks.json` in `country-income-trajectory`,
`treasury-yield-curve`, `worldbank-live`, `desktop-custom-contracts`,
`coauthor-*` — so a before/after pair would compare a run whose checks look for
`dp-spec.md` against one whose checks look for `dp-blueprint.md`. Both arms pass
by construction; the delta measures the checker edit, not the pack. Manufacturing
that number would make the ledger less trustworthy, so this entry carries the
evidence instead.

**What changed.** `dp-spec.md` is the prose-first, user-editable IR that
`nxd-run-job-loop` Step 1b authors and that discharges the policy read-back. It
is the one file in the loop the user is expected to open and edit, and "dp-spec"
read as a piece of internal schema vocabulary rather than as the plan document it
is. It is now `dp-blueprint.md`.

The rest of the family moved with it, because a stem that only half-renames is a
worse name than either whole:

| before | after |
| --- | --- |
| `dp-spec.md` | `dp-blueprint.md` |
| `dp-spec.approved.md` | `dp-blueprint.approved.md` |
| `dp-spec.lock.json` | `dp-blueprint.lock.json` |
| `dp-spec.proposal.json` | `dp-blueprint.proposal.json` |
| `dp-spec.proposal.approved.json` | `dp-blueprint.proposal.approved.json` |

**What deliberately did not change.** `dp-blueprint` names the artifact on disk;
`dp-spec` survives as the name of the schema and format layer, and is not stale
there. The `dp_spec_version` frontmatter key, the `nxd-dp-spec-lock-v2` / `-v3`,
`nxd-dp-spec-canon-v2` / `-v3`, `nxd-dp-spec-schema-*`, `nxd-dp-spec-proposal-v3`
and `nxd-dp-spec-diagnostic-*` envelope ids, the `dp_spec_authoring.py` /
`dp_spec_v2.py` / `validate_dp_spec.py` module names, the JSON-schema `title`
strings, and `docs/architecture/dp-spec-authoritative.md` all keep their
spelling. Renaming them would invalidate every lock and proposal already
written. The rule is recorded in that document so the next sweep does not have
to guess: an instance document follows the artifact, a file describing the
format does not. Two test fixtures were decided by it, both pure renames with
no content change (`git diff -M` records each at 100% similarity):
`dp-spec-v2-valid.md` → `dp-blueprint-v2-valid.md`, an instance document whose
every consumer already writes it out as `dp-blueprint.md`; and
`golden-dp-spec.lock.json` → `golden-legacy-dp-spec.lock.json`, which keeps the
old spelling in both its name and its `snapshot` / `source_basename` fields
*deliberately* — it is a `dp_spec_version: 2`, `plugin: 0.28.0` lock, so those
are the names that existed when it was written, and `golden-build-record.json`
is the same 0.28.0 build and names the same lock.

**Back-compat: how a pre-0.38.0 closure still verifies.** Only the **lock** needs
a filename fallback. `resolve_closure_lock()` prefers `dp-blueprint.lock.json`
and falls back to `dp-spec.lock.json`; the snapshot and proposal filenames travel
inside the lock as `snapshot` and `proposal_snapshot`, so once the lock is found
a legacy closure resolves the rest of itself from its own contents. `self_check.py`
runs inside the closure and cannot import that helper, so it carries an inlined
twin, `closure_path()`. When neither lock name is present the diagnostic still
reports the current one — a closure with no lock is a different fault from a
closure with an old one.

The same reasoning settles the two explicit-path surfaces. `--lock` takes a
literal path that the resume playbook itself prints as
`<closure>/dp-blueprint.lock.json`, so `resolve_lock_path()` substitutes the
legacy sibling when — and only when — the name asked for is the current one and
is absent; a genuine typo still reports itself. `--spec` gets no fallback at
all: the live IR is upstream of the closure, carries no hash, and is a path the
agent chooses rather than one a verifier resolves. That one is handled in the
skill instead — `context-and-resume.md` now tells the agent a pre-v0.38.0 job
has `dp-spec.md` and to rename it rather than re-author the plan, and the resume
reference gained the missing-live-IR case. It is recorded per command rather
than as another verdict row, because neither command reaches the verdict table
when `--spec` names a file that is not there: `materialized` exits 2 with
`could not hash …` on stderr and never calls `materialization_state`, while
`lock verify` exits 1 with `closure.live_spec_unparseable`. Filing it as a state
value would have pointed an agent at a code the command it ran does not emit.

Writing a fresh lock into an existing legacy closure now removes the pair it
supersedes, reporting `closure.legacy_artifact_superseded`. Leaving it produced
a closure carrying two approved plans with different hashes and two locks, where
every reader prefers the new names — so the stale pair was never read and never
reported, which is precisely the "two answers to what was this supposed to
build" that the byte-copy discipline exists to remove.

`source_basename` is **not** that mechanism, and an earlier draft of this entry
claimed it was. It is never dereferenced anywhere in `src/`: every read is a
write, a key-set membership check, or a non-empty-string shape check. It is
write-only provenance. The claim mattered because it was the stated reason no
fallback was needed, and it was wrong in the direction that hid two real
regressions — `lock verify` and Phase C both failed outright on a legacy closure
while the full suite stayed green, because no test used the old names.

A *live* `dp-blueprint.md` beside an in-flight job is still not searched for
under the old name; the fallback covers closures, which are the artifacts that
carry hashes and cannot simply be re-derived.

Frozen benchmark evidence — `ledger.md`, every `records/*`, every pre-existing
`entries/*` — was excluded from the sweep, per the "never rewrite" rule in
`AGENTS.md`. Those documents describe artifacts that were named `dp-spec.md` when
they were measured, and that is what they should keep saying.

## Evidence

- `evals/tests/test_legacy_closure_names.py` — 17 tests pinning the back-compat
  contract: `verify_lock` and `read_lock` on a legacy v2 closure built through
  the real `lock write` and then renamed, the live-spec cross-check still firing
  there, diagnostics naming the lock they actually read, a closure missing both
  names still reporting the current one, `closure_path()`'s three-way resolution
  executed from the shipped source, `LEGACY` covering every artifact (a gap there
  is a `KeyError`, not a fallback), and the inlined twin agreeing with the shared
  helper; the explicit `--lock` fallback and the typo it must not swallow; and
  the superseded-pair sweep. Verified to fail against the previous
  implementation: **16 of the 17 fail** with `src/nxd-run-job-loop/scripts/`
  restored to its pre-PR state (`git checkout origin/main -- …/scripts/`, tests
  held at their current state). The one that passes is
  `test_a_closure_missing_both_names_reports_the_current_one` — a closure with
  no lock at all already reported the current name, and that was correct before
  this change.
  Phase C is asserted over the shipped source rather than by running the script,
  for the reason `evals/tests/test_reach_gate_phase_e.py` already documents: reaching Phase C
  needs a complete valid closure, and a thin fixture exits in an earlier phase
  and passes vacuously. The first draft of this file made exactly that mistake.
  `finish()` is the exception and is exercised for real — it emits its report
  whatever the phases did, and its `spec_hash` read is the one drift site that
  produced no diagnostic at all.
  Phase C resolves the snapshot from `lock["snapshot"]` rather than guessing it
  by name, so the two verifiers cannot disagree about one closure: the lock
  schema permits an in-closure sub-path, and a name guess there would let
  `lock verify` pass while Phase C reported a missing snapshot and C8 silently
  skipped the plan. The name fallback is the last resort, for an unreadable
  lock. C1 reports that resolved name too, in both its message and its `path`
  argument: it was the last Phase C branch still emitting the constant, so a
  legacy closure with a deleted snapshot got `closure:dp-spec.approved.md` from
  `lock verify` and `closure:dp-blueprint.approved.md` from Phase C — two
  verifiers, one closure, two filenames, which is the disagreement the
  lock-resolved snapshot exists to prevent. C2 keeps the constant on purpose: it
  fires only when neither lock name exists.
  `closure_path()` uses `LEGACY.get()`, not a subscript — an unguarded
  lookup is the same crash-the-whole-run hazard this file documents for
  `CODES[code]`, and it runs inside a user's closure where a traceback is the
  worst possible output. The proposal has no `LEGACY` entry on purpose: its name
  travels in the lock, so an entry could never fire.
- `evals/tests/test_legacy_closure_names.py::test_every_code_self_check_emits_is_registered_in_its_own_table`
  — a defect the rename surfaced rather than caused.
  `closure.spec_hash_mismatch` was emitted from three Phase C branches while
  absent from `self_check.py`'s inlined `CODES` table, and `diag()` subscripts
  that table unguarded, so the first branch — a snapshot whose `dp_spec_version`
  disagrees with its lock envelope, precisely what a botched rename produces —
  raised `KeyError` and took the whole self-check down. The sibling vocab test
  checks self_check's codes against the *shared* registry; this checks them
  against the inlined one, which is the dict actually subscripted.
- `evals/tests/test_closure_layout_gate.py` — the carrying gate. It freezes the
  verify-before-build closure file list as a single string and asserts it appears
  verbatim in all four carriers (`nxd-generate-data-product/SKILL.md`,
  `nxd-run-job-loop/reference/scheduling.md`, `…/handoff-export.md`,
  `nxd-review-closure/SKILL.md`) plus both co-author prompts. Verified to fail
  against the previous implementation: with `src/` and `evals/public/` restored to
  their pre-rename state, 8 of its 9 tests fail — the four carrier checks, both
  `GENERATED_CLOSURE_FILES` checks, and both co-author prompt checks.
- `evals/tests/test_build_record_s0_producer.py`,
  `evals/tests/test_dp_diagnostics_schema.py`,
  `evals/tests/test_desktop_custom_contract_checker.py` — exercise the renamed constants
  end-to-end: lock write → `source_basename` → snapshot byte check → hash
  comparison, all against `dp-blueprint.*` paths.
- `evals/tests/_closure_files.py` — the frozen verify-before-build file list was
  copy-pasted byte-identically into two gate modules, both marked "frozen", so
  this rename had to edit both. It is now defined once and imported by both,
  following the `_harness.py` convention already used under `evals/tests/`.
- `uv run --no-project --with pytest --with duckdb --with pyyaml python -m pytest
  evals/tests -q` — 45 files had the filename token rewritten, and the suite is
  green on the new names.
- `cd evals/nxd_eval && uv run pytest -q` — 173 passed. The harness package does
  not reference the artifact and is unaffected.
- `python3 scripts/validate_skills.py --root .` — passes. `nxd-run-job-loop`'s
  `reference/dp-spec.md` moved to `reference/dp-blueprint.md` (`git mv`, so the
  rename is tracked) and its inbound link text in `SKILL.md` was updated with it;
  the `## Contents` requirement and the 500-line `SKILL.md` cap still hold.
- `./build-skills.sh` — packages, 200-entry cap respected on every skill.
- `python3 evals/benchmark_record.py --check` — entries and index valid.
- Three ASCII diagrams were realigned by hand rather than left ragged: the
  pipeline block in `nxd-run-job-loop/SKILL.md`, the closure tree in
  `nxd-generate-data-product/SKILL.md`, and the closure tree in
  `nxd-run-job-loop/reference/build-record.md`. The new stem is four characters
  longer, so a pure substitution breaks every column it participates in.
- Version lockstep: 0.37.4 → **0.38.0** (minor — the pack now writes a
  differently-named user-facing artifact, which is a behavior change rather than
  the packaging/doc fix a patch denotes), synced across
  `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and all 17
  `src/*/SKILL.md` `metadata.version` values. No skill added, so `current_pack`
  and the README table are unchanged.
