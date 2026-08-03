---
id: 2026-08-03-res-error-casing-convention-pinned
date: 2026-08-03
label: "res.error casing convention pinned; three corrections to the v0.33.0 ledger entry"
plugin_version: 0.33.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — res.error casing convention pinned; three corrections to the v0.33.0 ledger entry

## Notes

No eval arm exists and none can: this changes error-string casing in the harness
itself (`evals/run.py`) and adds a test. No public scenario observes the case of a
`res.error` value, and the strings are asserted on by no checker — a scenario
manufactured to grade them would produce a number that means nothing.

Three things happened here, and the third is the reason this entry exists rather
than an edit to `ledger.md`.

**1. The casing convention was invented where the codebase already had one.**
`run.py` holds 15 `res.error` assignments. The v0.32.0→0.33.0 codename sweep
capitalized three of them — `"Desktop preflight failed"` (:2222), `f"Desktop
runtime setup failed: {exc}"` (:2341), `f"Desktop harness infrastructure failure:
…"` (:2495), all introduced by `5b4d7e0` — on a "sentence-initial" rule authored
after the fact. The other twelve are lowercase, `"MCP server setup failed: …"`
being the lone acronym-initial exception, and the pre-rename text at those three
lines was `"pocket preflight failed"`, `"pocket runtime setup failed"` and
`"pocket harness infrastructure failure: …"` — lowercase, because a product name
in that slot followed the field's convention rather than overriding it. All three
are reverted. `res.error` renders through two sinks that treat it as an opaque
whole (`f"✗ ERROR — {res.error}"` and the JSON report's `"error"` field), so the
convention is simply: lowercase, always.

Also lowercased: the `RuntimeError` at :704, which is neither a log line nor a
`res.error` literal — both callers of `_desktop_runtime` catch it into
`res.error = f"desktop runtime setup failed: {exc}"`, so it renders mid-sentence.
Its sibling `RuntimeError` eight lines up was already lowercase and reaches the
identical sink. Still capitalized, correctly: `print(f"Desktop preflight OK: …")`,
a standalone stderr line, and the `res.verdict["summary"]` append whose leading
`{prior}` may be empty.

**2. The pin had a hole at exactly the strings being fixed.** A pre-merge review
found the first version of the test matched only literals assigned directly to
`res.error`, missing the two `*_infrastructure_error` helpers whose returns are
interpolated in verbatim — one of them `"desktop verifier facts were malformed"`,
lowercased in an earlier round. Re-capitalizing it passed the suite. The test now
parses `run.py` with `ast` and covers assignments plus those helper returns (15
strings, up from 13), which also retires the regex's blindness to single quotes
and `rf` prefixes: it fails closed on a form it does not recognize instead of
skipping it.

**3. The v0.33.0 `ledger.md` entry carries three factual errors that are NOT
corrected there.** It says "the other thirteen `res.error` assignments" and "§6
introduced the two anomalies … Both are reverted" — the real figures are 15
assignments and three anomalies, and its evidence list omits the third pre-rename
string. It also opens with a "five strings" tally that does not reconcile with its
own surviving-capitalized list. Those corrections were written and then withdrawn:
`ledger.md` became frozen evidence under the entry-migration contract
(`AGENTS.md`: *never append to or rewrite*), and "my rewrite is a correction" is
what every rewrite claims. The numbers stand there as merged; this entry is the
correction of record, and the figures above are reproducible by `git grep` from
the line numbers cited.

Worth naming plainly, since that entry's own thesis is that a reader can assume
every figure in it means something: it miscounted inside the paragraph correcting
a miscount. Four rounds of review were needed to reach a casing rule derived from
the code rather than asserted over it, and the entry documenting that is itself
the fourth data point.

## Evidence

- `evals/tests/test_env_var_names_match_docs.py` —
  `test_res_error_literals_are_lowercase` asserts every string reaching
  `res.error` starts lowercase, acronym-initial values excepted. Verified to fail
  against the previous implementation in both directions: re-capitalizing a direct
  assignment (`"Desktop preflight failed"`) and re-capitalizing a helper return
  (`"Desktop verifier facts were malformed"`) each trip it, where the earlier
  regex version caught only the first.
- `python3 -m pytest evals/tests` — 556 passed.
- `python3 scripts/validate_skills.py --root .` — passes.
- `python3 evals/benchmark_record.py --check` — passes.
- No `src/` skill, manifest or version surface is touched, so pack completeness
  and version lockstep are unaffected; the pack remains at 0.33.0.
