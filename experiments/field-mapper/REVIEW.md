# Layer-1 prototype — review outcome

**Verdict: NOT CLEAR. The prototype needs rework before transform integration.**

Two independent reviewers, both with executable reproductions:

- **Fable** — 1 critical, 4 high, 10 medium, 4 low
- **Sol** (`gpt-5.6-sol`) — 13 P0, 8 P1. Requirement verdict: *1 fail, 2 fail,
  3 fail, 4 fail, 5 incomplete, 6 fail*

The acceptance suite passes 6/6. **That result is not load-bearing** — see
[The suite does not validate what it appears to](#the-suite-does-not-validate-what-it-appears-to).

---

## Convergent findings

Independent agreement is the strongest signal here. Both reviewers found these
separately, and I reproduced each one myself before recording it.

### CV-1 — systemic failures land as a green partial run

`mapper.py:497` catches `SystemicError`, converts it to an `error` cell, and never
re-raises. Its docstring says "re-raised by the caller's gate" — but the gate
(`validate.py:718`) whitelists only three codes.

My reproduction:

```
2 ok, 2 error(code=cancelled), max_error_rate=0.6  ->  BLOCKED: False

budget_exceeded      blocked=False
model_not_found      blocked=False
grant_error          blocked=False
spec_error           blocked=False
credential_missing   blocked=True
```

A cancelled run, a budget-exhausted run, and a wrong-model run all land as if
complete. This defeats the design's central failure-policy claim. The
`CellError`/`SystemicError` type split is real in the hierarchy and **defeated at
the dispatch boundary** — the hierarchy was never the enforcement point.

### CV-2 — review ingress reintroduces emission-order identity

`__main__.py:220` builds `ordinal_to_key` from `emission_ordinal` (canonical
**sorted** order) but resolves `input_id` via `fixture.inputs.index()` (**file**
order). Reversing `inputs.json` binds a review for one ticket to another's row —
and because `bound_value_hash: "<derived>"` is then derived from that wrong
proposal, the misbinding **looks valid**.

This is exactly the failure the `target_row_key` machinery exists to prevent,
reintroduced in the one path a human reviewer actually authors through.

### CV-3 — `cmd_resolve` is a stub

`__main__.py:793` checks one CSV exists, prints two sentences, exits 0. It never
parses landed CSV, never calls `resolve()`, never applies a review, never runs an
assert. `--write-csv` persists only proposals and evidence — **not reviews**.

So the durable half of the review story has no operational path.

### CV-4 — grant refusal happens after source read

`Fixture.load()` (`__main__.py:140`) hydrates inputs and reads landed text before
`Grant.check()` runs inside `map_inputs` (`mapper.py:345`). CONTRACT §4 claims
refusal "before any source read"; that holds only for a *missing grant file*, not
a mismatched or expired one.

### CV-5 — live path can call a different model than the spec

`__main__.py:388` builds `TransportConfig` with `effort` only, so `model` falls
back to the default and `spec.model` is ignored. `TransportConfig.from_spec()`
exists to prevent precisely this and is never called. Reviews then bind to a
model that never ran.

---

## The suite does not validate what it appears to

The most consequential finding, and it undercuts the 6/6 result.

`bind_reviews()` (`__main__.py:202`) replaces `<derived>` placeholders with the
**current run's** value, input, and spec hashes. Fixture 06 — the one fixture
that supposedly proves auto-invalidation — uses `<derived>` for all three on its
override row. A changed proposal therefore *inherits* the review instead of going
stale.

Sol's check: `_verify_one()` never asserts the override, the effective source, or
the stale reason. **Removing review resolution entirely leaves fixture 06 green.**

The function's docstring anticipates this and claims safety: *"A review that pins
a REAL hash is left untouched... this function must not helpfully repair it into
a valid one."* That is true for the second row (`...dead`, which does go stale)
and false for the override row, which is the one carrying the load.

Corollary: my earlier read that fixture 06 proved the C2/P0-1 fix end-to-end was
**wrong**. It proves the stale path for a hand-pinned wrong hash, not the
auto-invalidation path for a real one.

---

## Sol-only P0s

- **Injection fence is escapable.** `transport.py:616` wraps source text in
  unescaped tags; a literal `</source_document>` in source breaks out. Beyond the
  fence: fixture 03 *requires* the injected score to land `ok`/`verified`/
  `blocks=false`, so machine semantics normalize the attack even though the README
  discloses it.
- **Null-bound overrides bypass input/spec invalidation.** When no proposal
  exists, `_binding_failures()` (`resolver.py:367`) returns before comparing
  `bound_input_snapshot_id` or `bound_mapper_spec_id`. An override bound to
  `old-input`/`old-spec` reproduces as current `human_override/ok`.
- **Row-level absence incorrectly blocks.** `validate.py:704` imposes an
  undeclared zero-`ok` floor; one honest `evidence_absent` cell with
  `max_absent_share=None` blocks — the inverse of the stated policy.
- **Fabricated evidence on an absent value bypasses validation.** The absent
  branch (`mapper.py:748`) returns before applying evidence violations, so a
  `verify_failed` atom does not propagate to `validation_failed`.
- **Orphan evidence passes `assert_bijection()`.** `resolver.py:288` checks
  evidence against synthesized effective cells rather than proposals; removing a
  proposal while keeping its evidence yields a synthetic `skipped` cell and the
  assert passes.
- **Overrides can violate typed coherence.** `records.py:410` permits an override
  type with an empty slot; both asserts accepted `TypedValue(INT, None)` as `ok`
  with a null wide value, and accepted a string override for an integer field.
- **Blocked builds still publish.** `__main__.py:777` writes CSV after the gate
  without checking `report.blocked` — fixture 04 exits 2 yet both files appear
  under `landed/`.
- **Publication atomicity unimplemented.** CONTRACT §7.7; `samples/README.md:304`
  admits there is no dlt fault-injection test.

## Fable-only findings worth acting on

- **H-2** — reviews whose row key vanished are neither applied nor surfaced as
  stale; the resolver iterates only current proposals. The most common
  invalidation case silently disappears, which CONTRACT §6.7 forbids.
- **H-4** — two divergent `normalize_text` implementations (`identity.py:100` vs
  `validate.py:206`). `text_hash` and `char_start/end` index different strings,
  and an honest verbatim quote containing a ZWSP returns `verify_failed` — a false
  hallucination verdict, the opposite direction from what "never fuzzy" defends.
- **M-6** — ledgers accumulate in the source tree with no `.gitignore`; a
  `git add .` commits per-attempt PII-adjacent logs. **Fix before any commit.**
- **M-8** — two same-named public vocabularies (`records.ValueStatus` vs
  `validate.ValueStatus`); the package root exports the wrong one, so
  `proposal.value_status is field_mapper.ValueStatus.OK` is `False`.
- **M-10** — grant ceilings of `0` are replaced by generous defaults via
  `or`-defaults; a grant meaning "spend nothing" authorizes $5.00.

---

## Status of the five carried design blockers

| Blocker | Status |
|---|---|
| C1 replace-load vs review state | **fails operationally** — structure exists, but CV-2, CV-3 and the null-bound gap lose or misbind review state through the paths a reviewer actually uses |
| C2 venv / SDK | **delivered** — dry-run runs the full suite without `anthropic`; live blocks with exit 2 for both missing-key and missing-SDK |
| C5 sentinel conflation | **partially delivered** — five-status enum, all-null typed slots, no string sentinel in a numeric column; but CV-1 punches through the systemic half |
| H4 consent enforcement | **partial** — a real library gate exists and is honest about not being a security boundary, but refusal is post-read (CV-4) and ceilings are unenforced |
| H2 substring for PDFs | **honest** — genuinely works for landed text (fixture 02 proves a paraphrase fails); unimplemented for PDFs and declared so. H-4 breaks the offsets/text_hash coherence it depends on |

---

## Design-doc corrections the implementation proved

1. **The type hierarchy is not an enforcement point.** `CellError` vs
   `SystemicError` reads as structural, but enforcement lives at the catch site
   and the gate's code list. Note 19 §3 should say so.
2. **"Before any source read" is not achievable with a load-then-check CLI
   shape.** Either the grant check moves into loading, or the claim weakens to
   "before anything leaves the machine."
3. **Content-derived keys don't survive a human-authored ingress by themselves.**
   Any path where a reviewer addresses a row by a readable id needs the same
   canonical ordering as `map_inputs`, or it reintroduces ordinal identity.
4. **A fixture that derives its own bindings cannot test binding.** Auto-
   invalidation needs fixtures that pin real hashes from a prior run.

## Still blocked

Unchanged by this review — both remain open:

1. **PDF text extractor** — nothing in the pinned venv extracts PDF text; adding
   `anthropic` does not address it.
2. **Where `mapper_reviews` physically lives** — and now sharper: `cmd_resolve`
   being a stub means the durable-review path has never actually run.

## Recommended order of work

1. CV-1 (systemic blocking) — the failure-policy claim is false until fixed
2. CV-2 + CV-3 (review ingress + `resolve`) — the review story is inert without both
3. Fixture 06 rebuilt to pin real hashes, so auto-invalidation is actually tested
4. M-6 `.gitignore` — before any commit
5. Orphan evidence, typed coherence, blocked-build publication
6. The rest by severity
