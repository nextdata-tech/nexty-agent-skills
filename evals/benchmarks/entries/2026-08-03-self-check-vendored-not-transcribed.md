---
id: 2026-08-03-self-check-vendored-not-transcribed
date: 2026-08-03
label: "nxd-generate-data-product: self-check shipped as an installed file, not a transcribed fence"
plugin_version: 0.34.1
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-generate-data-product: self-check shipped as an installed file, not a transcribed fence

## Notes

Step 7 used to tell the agent to copy a ~2,584-line `# self_check.py` python
fence out of `reference/self-check.md` verbatim into the closure. It now runs one
`cp` from the installed skill tree. That is an agent-facing instruction change, so
the default expectation is a measured paired entry — and the review that flagged
this PR reasonably assumed `generate-runnable-dp-from-intent` would supply it,
since that scenario exercises the generator through closure authoring.

**It does not, and the pair was run to find out rather than assumed either way.**
Both arms were executed — `main` (the fence route) and this branch (the `cp`
route) — same scenario, same skill set, same backends:

| arm | verdict | turns | tool calls | output tokens |
|---|---|---|---|---|
| `main` (transcribe the fence) | PASS 16/16 | 21 | 19 | 8,908 |
| this branch (`cp` the file) | PASS 16/16 | 23 | 21 | 9,909 |

The verdicts are the only line in that table worth reading, and even they are
weaker evidence than they look. Searching both transcripts for the thing under
test returns nothing:

```
self_check       0 occurrences   (both arms)
JOB_HELPER_DIR   0 occurrences   (both arms)
SELF-CHECK       0 occurrences   (both arms)
phase A ok       0 occurrences   (both arms)
```

Neither arm ran the self-check at all. The scenario's `prompt.md:47` hands the
agent a different script — `check_generated_closure.py`, a scenario fixture — and
its `acceptance-check` grades *that* script's `ALL CHECKS PASSED`. The closure
never gets a `self_check.py`, by either delivery route, because nothing in the
scenario asks for one.

So the 21→23 turn and 8,908→9,909 token deltas measure run-to-run variance on a
path this change does not touch. Recording them as a before/after effect would be
reporting noise as a result — and it would point the wrong way besides, which is
exactly how a manufactured number earns unwarranted trust when it happens to
point the right way. The figures are kept here because a reader who repeats the
run should find them already explained, not because they grade anything.

The absence generalizes. No `prompt.md` or `checks.json` under `evals/public/`
mentions `self_check` anywhere, including all 13 scenarios whose `checks.json`
names `nxd-generate-data-product`:

```
grep -rl "self_check" evals/public/*/prompt.md evals/public/*/checks.json   # no matches
```

Building a scenario that reaches Step 7 is the real fix and is not this PR's
scope — the self-check runs against an authored closure, so an arm that measures
it has to drive the generator all the way through Step 7 and then grade a
`self_check.py` run rather than a fixture's. Worth doing; it would also close the
gap that let the original transcription failure ship unnoticed.

What that failure was, since it is the reason the change exists: the agent was
told to run `python3 self_check.py`, the file was not on disk, and the entire
self-check was skipped in silence. The tell was `s1_structure: "not_reached"` in
the build record. A green banner over a check that never executed is worse than a
red one, and no eval arm caught it — which is the same gap this entry is
recording, seen from the other side.

## Evidence

- `evals/tests/test_skill_scripts_are_installable.py` — the carrying test. It
  gained the `self_check.py` installability assertions (pinned home under
  `src/nxd-run-job-loop/scripts/`, absent from the repo root, present in the built
  zip and on both install paths) and a new `test_self_check_copy_names_the_owning_skill`
  requiring every `cp` site to name `"$JOB_HELPER_DIR/scripts/self_check.py"`.
  Verified to fail against the previous implementation: appending
  `cp ../../self_check.py <closure>/self_check.py` to a skill doc trips it, where
  the first version of that guard — which also required `scripts/` on the line —
  let the same relative copy pass in silence.
- `evals/tests/test_policy_boundary_phase_d.py`,
  `evals/tests/test_reach_gate_phase_e.py`,
  `evals/tests/test_grant_gate_phase_g.py` — repointed from slicing the markdown
  fence to reading the shipped file. Every assertion is otherwise unchanged, including the
  Phase G byte-offset check that the consent gate exits before the transform
  import. Each retains an emptiness guard, so a missing file raises rather than
  slicing an empty string and passing vacuously.
- `evals/tests/test_self_check_diagnostic_vocab.py` — still enforces that the
  script's inlined vocabulary is a subset of `dp_diagnostics.CODES`, and still
  asserts the script never imports that module, which matters more now that both
  files share a `scripts/` directory.
- `python3 -m pytest evals/tests` — 594 passed, against 597 on `origin/main`. The
  net −3 is accounted for exactly: the fence-sync module (3 tests) is deleted
  along with `test_the_embedded_exception_is_real` (1), and
  `test_self_check_copy_names_the_owning_skill` (1) is added. The byte-identity
  guarantee those tests carried between the fence and the repo-root twin is
  retired rather than lost — with a single copy there is nothing left to keep in
  sync, and the assertions that replace it check the shipped file's presence and
  provenance instead.
- `python3 scripts/validate_skills.py --root .` — passes.
- `python3 evals/benchmark_record.py --check` — passes.
- Version lockstep holds at 0.34.1 across `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, and all 17 `src/*/SKILL.md`. No skill is
  added or removed, so pack completeness is unaffected.
