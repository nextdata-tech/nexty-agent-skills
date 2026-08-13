---
id: 2026-08-13-labeled-root-loop-unroll
date: 2026-08-13
label: "evals: labeled-root checkers read a looped closure as they read an unrolled one"
plugin_version: 0.37.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — evals: labeled-root checkers read a looped closure as they read an unrolled one

## Notes

No scenario arm can distinguish this change, and measuring one would actively
mislead.

**Nothing under `src/` changed.** No skill text and no recipe: an agent authors
the identical closure before and after. What changed is whether a correct
closure is READ correctly. A measured arm would differ only by which spelling
the agent happened to choose that run — which is the very nondeterminism this
fixes the checker against, so the number would be reporting the coin flip.

**The defect was found by CI, not by a hypothesis.** `multi-source-labeled-roots`
went PASS → FAIL on the `run-evals` gate for
[PR #181](https://github.com/nextdata-tech/nexty-agent-skills/pull/181), a PR
that changes no skill and does not touch that scenario. The agent produced a
correct closure: both labeled roots pinned to `NXD_TRANSFORM_ROOT`, then read
in a loop.

```python
for source_root, model in ((orders_root, "orders"), (users_root, "users")):
    reader = filesystem(bucket_url=str(source_root / model), file_glob="*.csv") | read_csv()
```

`check_labeled_multi_source.py` propagates root-ness through `ast.Assign` and
`ast.AnnAssign` only, so `source_root` never entered `root_names`, and `model`
never resolved to a label — `transform-uses-pinned-root` failed a closure that
is correct, and arguably the better of the two spellings. The baseline PASS had
been recorded from a single observation of an agent that happened to write it
unrolled, which is exactly what that cell's baseline note warned about
("Re-measure before treating a future flip as a skill regression").

This is the same class of defect as the `urllib.parse` false positive fixed
earlier in the same PR: keying on a bound name rather than resolving what it
refers to. The checker had partial loop handling already, but only for tuples
whose elements are ALL string constants, so `(orders_root, "orders")` fell
through it.

**What landed.** `evals/tools/loop_unroll.py` normalizes literal `for` loops
into the statements they are shorthand for, before analysis. The alternative was
loop-awareness in each of the six places that consume those name sets; rewriting
the input instead means every downstream check inherits the fix. Both labeled-root
checkers call it at their transform-parse site.

Deliberately narrow: literal `tuple`/`list` iterables (including one hop through
a name bound to one), `zip()` and `enumerate()` of literals. Loops carrying
`break`/`continue` are left alone — unrolling asserts every iteration's body
runs, which is what those statements deny — as is anything else, so an
unanalyzable loop fails exactly as it does today rather than silently passing.

**Verified as an A/B on the checker that actually failed**, driving
`check_labeled_multi_source.py` end-to-end over a built closure:

| spelling | without the fix | with the fix |
|---|---|---|
| unrolled (what the baseline saw) | exit 0 | exit 0 |
| looped (what CI saw) | `FAIL transform-uses-pinned-root` | exit 0 |

The negative direction is pinned too: an unpinned loop (`Path.cwd()`) and a
partially-pinned loop are both still rejected, so unrolling makes more closures
readable rather than more closures acceptable.

Two bugs in the unroller were caught by its own tests before commit — synthesized
nodes were unparsed without locations when a nested loop was expanded, and the
nested-`break` prune broke the wrong loop, so an inner `break` wrongly blocked
the outer loop.

## Evidence

* `evals/tests/test_loop_unroll.py` — five equivalent spellings of one correct
  closure all pass; unpinned and partially-pinned loops still fail; the
  expansion rules (nesting, flow control, rebinding, bounds, non-literal
  fallback) are pinned individually. Fails against the previous implementation.
* `evals/tests/test_worldbank_connector_gate.py::test_every_evals_tool_is_classified`
  — required the new shared module to be mapped to its importing scenarios in
  `affected_scenarios.py`, which is how a change to it selects those two
  scenarios instead of reading as "no eval was affected".
