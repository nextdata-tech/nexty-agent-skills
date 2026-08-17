---
id: 2026-08-03-res-error-casing-convention-pinned
date: 2026-08-03
label: "res.error casing convention pinned; a v0.33.0 ledger figure corrected"
plugin_version: 0.33.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — res.error casing convention pinned; a v0.33.0 ledger figure corrected

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
`res.error` literal — the caller at :2337 catches it into
`res.error = f"desktop runtime setup failed: {exc}"`, so it renders mid-sentence.
(The other caller, :2211, routes it to `res.metrics["desktop_preflight_error"]`
and sets the fixed `res.error = "desktop preflight failed"`, so it never
interpolates the message.) Its sibling `RuntimeError` eight lines up was already
lowercase and reaches the same `res.error` sink. Still capitalized, correctly: `print(f"Desktop preflight OK: …")`,
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

**3. The v0.33.0 `ledger.md` entry overstates one figure, and it cannot be fixed
there.** Its §8 reads: *"sentence-initial lowercase `desktop` in eight `run.py`
strings that reach benchmark reports and the judge (two beyond those reported)"*
(`ledger.md:1277`). The real count is **seven**:

```
git show 5b4d7e0 -- evals/run.py | grep -cE '^\+.*Desktop [a-z]'   # 7
```

Two log lines (:704, :903), the helper return (:1037), the three `res.error`
assignments (:2222, :2341, :2495), and the `res.verdict["summary"]` append. "Eight"
matches no commit.

That entry is frozen evidence under the entry-migration contract (`AGENTS.md`:
*never append to or rewrite*), so the figure stands there as merged and this entry
is the correction of record. An earlier revision of this PR did rewrite it in
place; those edits were withdrawn on the rebase that brought the freeze in,
because "my rewrite is a correction" is what every rewrite claims.

Worth naming plainly, since that entry's own thesis is that a reader can assume
every figure in it means something: it miscounted while documenting a miscount.
Four review rounds were needed to reach a casing rule derived from the code rather
than asserted over it, and the entry documenting that is itself the fourth data
point. Every figure in *this* entry is reproducible from the commands and line
numbers cited beside it — which is the only defensible way to write the correction.

## Evidence

- `evals/tests/test_env_var_names_match_docs.py` —
  `test_res_error_literals_are_lowercase` asserts every string reaching
  `res.error` starts lowercase, acronym-initial values excepted. Verified to fail
  against the previous implementation in both directions: re-capitalizing a direct
  assignment (`"Desktop preflight failed"`) and re-capitalizing a helper return
  (`"Desktop verifier facts were malformed"`) each trip it, where the earlier
  regex version caught only the first.
- `python3 -m pytest evals/tests` — 597 passed (596 on `origin/main`; this PR adds exactly the one test named above).
- `python3 scripts/validate_skills.py --root .` — passes.
- `python3 evals/benchmark_record.py --check` — passes.
- No `src/` skill, manifest or version surface is touched, so pack completeness
  and version lockstep are unaffected; the pack remains at 0.33.0.
