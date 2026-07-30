# Fix design for the live-execution findings (L1–L5)

Scope: turn SPEC-CHANGES.md's live findings into concrete fixes and check what
they invalidate. REVIEW.md's ~30 findings are assumed known and are cited only
where load-bearing. Everything asserted below as behavior was reproduced in this
worktree on 2026-07-30; each reproduction is marked **[repro]**.

Baseline: `python3 -m field_mapper verify samples` → 7/7 **[repro]**.

---

## Part A — L1: a stable wrong value lands `ok` with no signal

### The shape of the problem, stated precisely

On a media-direct cell the harness has *zero* mechanical connection between the
value and the source. Every check that ran on the haiku misread was a check on
the value's **form** (type, range, atom count), not its **relation to the
source**. The one relational check (`verify_quote`) is structurally inapplicable
(`landed_text is None` → `UNVERIFIED`, `validate.py:389`). And the review
system's detection mechanism — staleness on change — is calibrated for
*instability*: a stable wrong answer produces no `value_changed`, confirms
cleanly, and binds forever.

So there are two separable harms:

- **H-value**: the wrong number itself lands.
- **H-dressing**: the harness *dresses* it as grounded — a fabricated quote
  (`'$30.00'`) discharges `min_evidence: 1`, the cell reads `ok`, and a later
  confirmation is indistinguishable from a confirmation of a checked cell.

No single mechanism fixes both. Below: three mitigations worth building, two
rejected with reasons, and the enforcement chain that turns the current preflight
warning into something with teeth.

### A1. Cross-field structural checks — REBUILD THE REDUNDANCY (cheap, deterministic)

**Mechanism.** A new spec-level declaration, closed vocabulary, no expression
language:

```json
"cross_field_checks": [
  {"kind": "product_equals", "factors": ["quantity", "unit_price"],
   "target": "total_usd", "tolerance": 0.005},
  {"kind": "sum_equals", "terms": ["subtotal", "tax"], "target": "total_usd"}
]
```

Enforced in `validate.py` (a new `check_cross_field` alongside
`check_range`), evaluated per response in `mapper._validate_response` after the
per-field pass. A violation attaches to the `target` field (and names the
factors), flows into the **existing retry loop** — so the correction turn says
"quantity=2 × unit_price=45.00 ≠ total_usd=30.0" and the model gets a bounded
chance to re-read. Exhaustion → `validation_failed`, value discarded, exactly
like a range violation. Hashed into `mapper_spec_id` (semantic). Numeric
tolerance is for float representation only, never a fuzzy match on strings.

**Cost.** Zero extra calls. ~80 lines across `spec.py` / `validate.py` /
`schema.py` routing table / one fixture. The real cost is authorial: the spec
must *extract the redundant fields* (qty, unit price, subtotal) for the check to
have anything to bite on. Preflight should say so for media-direct specs:
"declare and extract the artifact's internal redundancy; it is the only
mechanical check this path has."

**Catches.** Internally-inconsistent misreads — the model reads `2`, `45.00`,
and `30.00` and the arithmetic exposes one of them. On the actual L1 image
(`2 AT 45.00 … TOTAL 90.00`, if the line items were in frame), this fires.

**Does NOT catch.** *Consistent* misreads (qty misread as `1` alongside total
`45.00` — wrong and self-consistent); artifacts with no internal redundancy
(the current 240×96 fixture crop shows only ref + total — the check has nothing
to bind unless the spec widens the crop and the fields); non-numeric fields.

### A2. Cross-model corroboration — the only mechanism that demonstrably catches this exact instance

Sonnet and a direct read both return $90.00; haiku stably returns $30.00. The
disagreement is real, cheap to detect, and currently invisible.

**Mechanism.** A spec field, legal only when `accepts_media` is non-empty:

```json
"corroboration": {"model": "claude-opus-5"}
```

For each **media-direct input** (per input, not per cell — one call covers all
fields), after the primary response validates, the mapper makes one additional
call with a `TransportConfig` derived from the corroboration model (capability
gating via `supports_reasoning_controls` applies independently — that is why the
knob must be a model id, not a config copy). Compare per-field typed values:
strings after `normalize_text`, numbers exact, bools/enums exact. No tolerance,
no similarity — fuzz here reopens the hole the substring check refuses to open.

- **Agreement** → cell stays `ok`, evidence stays `evidence_unverified`.
  Agreement is corroboration, not verification; the statuses must not upgrade.
- **Disagreement** → cell lands `validation_failed` with a `corroboration`
  violation naming both models and both values, value **discarded** (we know one
  is wrong but not which; landing either is a coin flip), `needs_review=True`.
  The reviewer sees both readings next to the artifact — a well-posed human
  question instead of a silent landing.

Accounting: `estimate()`/`calls_per_cell` and the budget ledger must count the
extra call; the ledger records the corroboration attempt with its own
`model_snapshot`. **Grant impact**: the grant binds one model (`grant.py`
`model` field — and L1 finding #1 showed that binding firing live). The grant
schema needs a `corroboration_model` field; a corroborating run under a grant
that doesn't name the second model must refuse, same as the model-mismatch
refusal that already works.

**Cost.** ~2× calls and latency on media-direct inputs only (the call can run
concurrently with nothing else; it is serial after the primary's validation).
Moderate complexity: a second config, grant extension, budget arithmetic.

**Catches.** Stable single-model misreads where the models' failure modes are
uncorrelated — L1 exactly. Also absorbs some L2: a primary/corroborator flip on
a genuinely unstable cell surfaces within one run instead of as cross-run
staleness.

**Does NOT catch.** Correlated misreads (both models misread identically —
plausibly on genuinely ambiguous or degraded artifacts, or shared
training-data biases). Two agreeing models on a blurry scan is still
unverified, and the statuses say so. Also: a disagreement on an ambiguous
artifact produces review load, not answers — on a low-quality corpus this
converts silent wrongness into visible reviewer cost, which is the honest trade
but a real one.

### A3. Stop letting unfalsifiable evidence discharge the evidence obligation — the harder refusal, with the right teeth

The question posed: should media-direct + `min_evidence > 0` be a harder refusal
than a warning? **Yes — at `map_inputs` time, as a `SpecError` (systemic,
blocks), not at construction.**

**Mechanism.** In `map_inputs`, after quarantine and before any dispatch:

```
if any(item.is_media_direct for item in survivors) and spec has any field
with min_evidence > 0  →  raise SpecError (blocks, before any call):

  "field(s) X, Y declare min_evidence > 0, but N media-direct input(s) can
   never produce a checkable evidence atom — a quote about an artifact the
   harness cannot read is unfalsifiable and must not discharge an evidence
   obligation. Set min_evidence: 0 on these fields to run evidence-blind.
   That edit changes mapper_spec_id, so the existing grant stops matching
   and consent must be given again against a spec that admits it."
```

That last sentence is the point. The current preflight warning is advisory
console text; this chain makes the trade land in three durable places:

1. the **spec** now says `min_evidence: 0` — the blindness is declared, hashed;
2. the **`mapper_spec_id`** changes — every prior review unbinds, correctly,
   because "evidence required" → "evidence waived" is a semantic change;
3. the **grant** stops matching — a human re-consents to a spec that states it
   runs evidence-blind. The consent gate demonstrably fires live (L1 §1), so
   this is enforcement that already works, pointed at the right thing.

Why not construction-time: the landed decision (SPEC-CHANGES §1) is right that
an unbuildable spec is un-inspectable — `preflight` must still run and explain.
Why not per-cell (counting only checkable atoms toward `min_evidence`): that
shape burns validation retries on an unsatisfiable constraint — the model can
*never* produce a checkable atom on this path, so retrying is spending money to
rediscover a static fact. The static fact should refuse statically.

Keep requesting the evidence array in the wire schema regardless: on
media-direct the atoms are locator *descriptions* ("third row, right column,
after the TOTAL label" — which is what fixture 07's recorded response models),
useful for human triage. But note what the live run exposed: haiku returned a
verbatim-shaped `'$30.00'`, not a region description. The instruction for
media-direct specs should explicitly ask for region descriptions and say
verbatim quotes are meaningless here — small prompt change, worth making when
the fixture is updated.

**Fixture impact.** `samples/07-media-direct/spec.json` currently declares
`min_evidence: 1` on both fields **[repro]** — the fixture itself demands
evidence the path cannot check. Update it to `min_evidence: 0` (grant re-derives
via `<derived>`), and add a small negative fixture asserting the refusal fires.

**Catches.** Nothing about the wrong value — this is entirely an H-dressing fix.
It removes the false signal ("evidence present, obligation met") that made the
L1 cell look like every other `ok` cell.

### A4. "Approved but unverifiable" — mark it, don't invent a new approval kind

Should confirmation binding get a new concept? A *smaller* one than a new
verdict. A human confirming a media-direct cell looks at the artifact and the
value — that human check **is** the only verification this path has, so the
confirmation is legitimate and should not be second-classed or expiring. What
must change is that downstream cannot currently tell it apart.

**Mechanism.** The effective cell / provenance sidecar gains one boolean column,
`evidence_unfalsifiable` (true when the winning proposal's atoms are all
`evidence_unverified` **and** the input was media-direct), populated by
`resolver.resolve()` from data the `Resolution` bundle already holds. The review
queue projection (GENERALITY S13) renders those rows with the artifact reference
and a banner: "the quoted text below is a model claim about the artifact, not a
checkable quote — verify against the artifact itself." No new `Verdict`, no new
`EffectiveSource` value, no TTL.

Note what already works and should be said out loud: the media digest is in
`snapshot_projection` (`mapper.py:176`), so **swapping the artifact already
unbinds the confirmation** as `input_changed`. The un-detectable case is only
"same artifact, stably wrong model" — which is A2's job, not binding's.

**Dependency.** This touches resolver output and the review surface, both of
which are inert until REVIEW.md CV-3 (`cmd_resolve` is a stub) and CV-2 (review
ingress ordinal bug) are fixed. Do not build A4 before those; a marking column
on a path no reviewer can actually exercise is decoration.

### Rejected: self-consistency across N same-model calls

k calls to the same model on the identical request, majority vote or
disagreement-flag. **Rejected as an L1 answer**: L1 is *defined* by stability —
four consecutive identical wrong answers. Same-model resampling is blind to it
by construction, and costs k×. It does convert L2-class flakiness into
within-run signal, but A2 already buys that as a side effect for less blindness.
If A2's second model is unaffordable for some population, self-consistency is
the weaker fallback — say so in the spec docs, don't build it first.

### Rejected: same-model transcribe-then-extract round-trip

Call 1 "transcribe the region verbatim", land it, call 2 extract with quotes
substring-checked against call 1. This restores a mechanical check whose anchor
is the same model's reading — haiku's transcript of that line would say
`$30.00`, and the check would *certify* the misread (GENERALITY S4c's downgrade,
now with a demonstrated instance). Same-model round-trip catches
**fabrication between stages**, not **misreading**; with a different transcriber
model it collapses into A2 at the same cost. Not worth building as an L1
mitigation.

### What the harness still cannot do after all of A1–A4

A stable, correlated-across-models misread of an artifact with no internal
redundancy lands `ok` (with `min_evidence: 0` declared, unfalsifiable-marked,
and consented to). That residual is irreducible without a text layer — it is
what "evidence-blind" means, and the fixes above make the harness *say* it
rather than pretend otherwise. The genuine fix remains staged extraction
(SPEC-CHANGES ext. 3) or, for text PDFs, Part B.

---

## Part B — L4: the citations fork

### Recommendation

**Adopt citations as a per-spec evidence mode for text-PDF specs — single call,
schema requested in prose, harness-validated after the fact.** Concretely:

```json
"evidence_mode": "structured" | "citations"   // default "structured"
```

- `structured` — today's path, unchanged. Mandatory for images, scanned PDFs,
  landed-text specs (citations are impossible or pointless there).
- `citations` — legal only when `accepts_media` includes `application/pdf` and
  the spec is media-direct for those inputs. The request carries
  `"citations": {"enabled": true}` on the document block and **no
  `output_config.format`** (the 400 incompatibility, already recorded in
  CONTRACT §"schema.py split"). The instruction requests the JSON shape in
  prose; the response is parsed by searching for the JSON body and validating
  it against the compiled schema **post hoc** — the machinery `providers.py`
  already built and debugged for `claude_cli` (fence search, trailing-prose
  tolerance), promoted from "development-provider weakness" to a deliberate,
  bounded trade on the paid path. A non-conforming response is a
  `SCHEMA_REJECT` and burns a validation retry; it can never land.

### Why this fork, and why single-call

**The trade is schema-guaranteed parse vs fabrication-proof evidence, and for
this harness evidence is the scarcer good.** The wire schema was never the load-
bearing enforcement anyway — CONTRACT §8's whole point is that the API cannot
express most constraints and `validate.py` re-checks everything (type, enum,
range, length) after parse. What `output_config.format` uniquely buys is "the
response parses"; losing it costs retries on malformed output, never
correctness. What citations uniquely buy — `cited_text` extracted by the API,
never authored by the model, with page locations, free of output-token cost —
is the property the entire two-stage design was built to reconstruct.

**Why not the two-call shape** (citations call for evidence + structured call
for values): the join is incoherent. A citation from call 1 supports call 1's
answer; binding it to call 2's value asserts a relation nobody checked, and L2
demonstrated the two calls can genuinely disagree (`ok` vs `evidence_absent` on
the identical input). Two calls also double cost and double the nondeterminism
surface. The one-call shape keeps value and evidence from the same utterance,
which is the binding the whole records model assumes.

**Why per-spec, not global**: the mode is meaningful only where a text layer
exists server-side. Scanned PDFs are "not citable" and image citations do not
exist — so this fork does **not** rescue Part A. Fixture 07's case is untouched;
`evidence_mode: citations` on an image spec is a construction-time `SpecError`.

### Vocabulary: `verify_status` needs a fourth value

`cited_text` is not `verified` — that value's contract is "the harness ran a
substring check against landed text it holds, re-checkable by anyone from
`text_hash` + offsets." An API citation is a *stronger claim by a different
verifier that the harness cannot locally re-check* (it holds only base64).
Conflating them would corrupt the audit meaning of `verified`.

Add `VerifyStatus.API_CITED = "api_cited"`: "the quote was extracted from the
document by the API, not authored by the model; fabrication is structurally
impossible; the harness did not and cannot re-check it locally." Gate treatment:
counts as verified-equivalent (not into `unverified_share`). Locator: reuse
`page` for `start_page_number` and add `page_end`; `locator_kind` stays
`PAGE_REGION`-adjacent or gains `API_CITATION`. `extractor` /
`extractor_version` carry `"anthropic-api-citations"` + the `anthropic-version`
date, which is exactly what those columns were designed for.

Consequential simplification: on the citations path there is **no haystack**,
so REVIEW H-4 (divergent `normalize_text` implementations) is not load-bearing
for it — the mode has no substring check to disagree about.

### What it changes in the two-stage design

For **text PDFs**, stage-1 extraction becomes unnecessary: the mapper runs
single-stage with API-verified evidence. The two-stage design remains the story
for images, scans, and audio. The residual PDF blockers narrow to exactly
SPEC-CHANGES' revised list: page counting for splitting (600-page/context
ceilings), scanned PDFs (OCR or evidence-blind), and multi-row output (ext. 2).

### Sequencing

Decide now (this document is the decision); build when a PDF spec actually
exists — there are currently zero PDF fixtures. It depends on no REVIEW.md fix.
Reserve the `evidence_mode` key and the `api_cited` value in CONTRACT §2.3 and
§8 immediately so nothing else claims the design space, and rewrite the two
stale "circular / no extractor" claims (Part D, items 2–3) in the same edit.

---

## Part C — L3 and L5

### L3: capability handling

**The prefix table is the right *offline* shape and the wrong *only* shape.**
Keep `_REASONING_CONTROL_MODELS` + unknown-means-no as the no-network fallback
(dry-run and preflight must work with no SDK). Add a live probe through the
provider seam: the Models API publishes exactly this
(`client.models.retrieve(model).capabilities` →
`thinking.types.adaptive.supported`, `effort.supported`). `AnthropicProvider`
gains `capabilities(model)`; `transport.Client` resolves once per run, caches,
and prefers the API's answer over the table, recording a ledger note when they
disagree. One free request per run; fixes the table's two structural defects:

- **Staleness**: a future model family the table doesn't name is wrongly
  degraded forever (conservative, but silently — the run succeeds at lower
  quality with nothing recorded).
- **Bit conflation**: the table treats adaptive-thinking and `effort` as one
  capability because they arrived together — but they are separate leaves in
  the capability tree, and models exist where they diverge (Opus 4.5 supports
  `effort` low/medium/high but not adaptive thinking). One boolean cannot
  represent that; two probed leaves can.

**Other universal-model assumptions found in the sweep** (the question "what
else assumes one family"):

1. **`_build_request` sends `thinking: {"type": "disabled"}` unconditionally
   when `thinking_enabled=False`** (`transport.py:1072`) — the else-branch is
   not gated on `supports_reasoning_controls`, so a pre-4.6 model with thinking
   explicitly disabled receives a thinking param from the 4.6+ dialect. Not
   live-verified (would need a key), but it is the same defect class L3 was:
   a 4.6-generation knob presumed universal. Fix: when the model lacks
   reasoning controls, omit `thinking` entirely on **both** branches.
2. **`_validate_thinking_effort_pairing`** encodes a `claude-opus-5`-specific
   rule (disabled-above-high 400) and applies it to every model, including ones
   where `effort` will never be sent. Harmless today (it only *refuses*), but
   it should be scoped to models where the controls are actually emitted.
3. **`_USD_PER_MTOK_*`** — Opus-only (L5, below).
4. **`_MAX_PDF_PAGES_PER_REQUEST = 600`** — correct only at a 1M context
   window; 100 under 200K (haiku). Currently dead code either way (see L5).
5. **`max_tokens=16_000` default + "thinking is on by default here"
   comments** — sized for a thinking-on Opus model; on a non-reasoning model
   the same value is a harmless overshoot, but the comment states a
   model-specific fact as a transport fact.

**What a 400 handler should say when it does not know the cause.** The current
`BadRequestError` branch (`transport.py:1234`) asserts "Common causes: an
unsupported JSON Schema keyword … or thinking disabled above high effort" — a
confident diagnosis that was wrong in the one live incident. Replace with three
rules:

1. **State only what is mechanically known**: the API refused the request
   before executing it; it blocks; the same request fails on every cell.
2. **Hypotheses, ranked, labelled as hypotheses** — "the harness cannot see
   which parameter was refused; candidates, most likely first: (a) a reasoning
   control on a model that does not support it [now gated by capability
   detection — if you see this, the table/probe is wrong, which is itself the
   finding], (b) an unsupported JSON Schema keyword, (c) thinking disabled
   above `high` effort."
3. **An opt-in escape hatch for the API's own words**: on
   `FIELD_MAPPER_DEBUG_400=1`, print the SDK exception's message to **stderr
   only** — never the ledger, never `error_detail`. The redaction policy
   (`_redact_status`) is right for durable surfaces; it is what forced the
   harness to *guess* in the incident. A deliberate, ephemeral, operator-chosen
   stderr print resolves the tension without weakening the ledger contract.

### L5: the media cost estimate

Four defects, one of them new **[repro]**:

1. **`cmd_preflight` drops `spec.model`** (`__main__.py:695`,
   `TransportConfig(effort=spec.effort)`), so a haiku spec is priced at Opus
   rates **with `pricing_is_approximate=False`** — the flag designed to catch
   this cannot fire because the model it would compare was discarded.
   Reproduced: preflight path → `model=claude-opus-5, approximate=False,
   $1.2081`; `from_spec` path → `approximate=True`, same dollars. This is
   REVIEW CV-5's shape at a second call site, *after* CV-5 was fixed at the
   first — which argues the fix is not "edit this call site" but "remove the
   footgun": give `TransportConfig` no default-model constructor path in CLI
   code, or lint that `__main__.py` never calls `TransportConfig(` directly.
   Minimum fix: `config=TransportConfig.from_spec(spec)` + print a pricing
   caveat line whenever `pricing_is_approximate or not token_counts_measured`.
   (SPEC-CHANGES' claim that "`pricing_is_approximate` flags it" is itself
   wrong for the preflight path — see Part D item 8.)
2. **Rates are Opus-only.** Replace the two constants with a prefix-matched
   per-model table (opus-5/4.x $5/$25, sonnet $3/$15, haiku-4-5 $1/$5, fable
   $10/$50 — same shape and maintenance burden as
   `_REASONING_CONTROL_MODELS`). Unknown model → price at the **most expensive
   known rate** and set `pricing_is_approximate` — errs high without refusing.
3. **PDF pricing must be per page; byte pricing errs low, violating the
   estimator's one stated principle.** Since the harness has no PDF library:
   - Best-effort page count with **stdlib**: scan the raw bytes for
     `/Type /Page` objects (tolerant of whitespace variants, excluding
     `/Pages`). Works on ordinary non-encrypted PDFs; when the scan finds
     nothing plausible, the artifact is *unpriced* (below).
   - Price a counted PDF at `pages × (3000 text + 4800 image) tokens` — both
     documented per-page maxima, so the figure is a ceiling, restoring
     err-high.
   - Price an **image** at a flat 4,784 tokens (the documented per-image cap at
     high-res) instead of bytes — errs high with no library.
   - Delete `_PDF_TOKENS_PER_KB`.
4. **Is a deliberately-refusing estimate better than a wrong one? For the
   gate, yes — with an override; for the run, the ledger is the backstop.**
   Two changes:
   - An **unpriceable** artifact (url/file_id, or a PDF whose page count the
     scan cannot determine) should be a `fits_within` breach — "cannot bound
     spend for N artifact(s)" — refusing at preflight unless the operator
     passes `--allow-unpriced` (or the grant declares it). Today the floor is
     printed and the run proceeds under "fits within ceilings" — a consent
     gate that waves through the thing it cannot measure.
   - State the real blast radius honestly: `BudgetLedger` reconciles to
     actuals and stops mid-run, so an estimator error can never exceed
     `max_usd` — it wastes a doomed partial run (skipped cells → blocked
     build), it does not create unbounded exposure. That bound is why the
     estimator can afford to be a coarse ceiling; the printout should label the
     number "worst-case bound", not "spend", because `per_call_output =
     max_tokens × retries` already makes it one (16,000 estimated vs 75 actual
     output tokens in the live run — the max-tokens term, not the rates, was
     the largest single error factor).
   - While in there: the dead `_MAX_REQUEST_BYTES` should actually be enforced
     at preflight for base64 media (`ceil(bytes × 4/3)` + text per call vs the
     ceiling), which SPEC-CHANGES already calls for and nothing implements
     **[repro: constant has zero call sites]**.

---

## Part D — invalidation sweep

New code findings first (neither is in REVIEW.md):

**D-1 (new bug, high). `map_inputs` re-stamp drops `accepts_media` from the
spec hash.** `mapper.py:359–374` reconstructs `MapperSpec` field-by-field when
`harness_version` is empty and omits `accepts_media` — the *exact* trap
SPEC-CHANGES documents as found-and-fixed in `_stamp_harness_version`
("Now `dataclasses.replace`. Any future spec field would have hit the same
trap."). The CLI path pre-stamps in `Fixture.load` so fixtures dodge it, but
any in-process caller (the stated Layer-1 use: a transform invoking
`map_inputs` directly) hits it. Reproduced: a media spec run through the
re-stamp block hashes `7a7168c8…` (accepts_media silently `()`), vs
`c6a9f62d…` via `dataclasses.replace` — so a media-accepting spec and its
text-only twin share a `mapper_spec_id`, the grant matches a spec the user
never saw, and reviews bind across the two. Fix is one line:
`bound_spec = dataclasses.replace(bound_spec, harness_version=__version__)`.
SPEC-CHANGES' "Extension 1 — LANDED" section should note the second site was
missed, because it presents the trap as closed.

**D-2 (new, low). `spec.with_wire_schema` passes `accepts_media=list(...)`**
(`spec.py:705`) where every other path holds a tuple — hash-neutral
(`to_canonical` re-lists) but a frozen dataclass now carries a mutable field
and tuple-vs-list breaks dataclass equality between otherwise-identical specs.
Same fix shape: build via `dataclasses.replace(self, wire_schema=…)`.

Stale or overstated claims, with what they should say:

1. **ARCHITECTURE.md:5 and :298** — "Acceptance suite passes 6/6" / "`verify
   samples` — 6/6 pass", and the fixture table lists 01–06 only. The suite is
   **7/7 [repro]**; add fixture 07's row (and its live-run caveat, item 6).
2. **ARCHITECTURE.md "Blocked on" §1 (:352)** — "Nothing in the pinned venv
   extracts PDF text, and adding `anthropic` does not solve it." The correction
   block higher in the same file (:227) contradicts this: for **text PDFs** the
   API extracts text server-side and citations return unfabricatable spans, so
   adding `anthropic` *does* address the text-PDF case. The Blocked entry
   should be rewritten to the narrowed residual: page counting for splits,
   the citations/structured fork (decided in Part B above), scanned PDFs.
3. **CONTRACT.md open question 4 (:618–625)** — same two claims verbatim:
   "adding `anthropic` does not address it" and "sending the PDF to the API
   and landing the returned text makes the substring check circular (explicitly
   forbidden)." The second is now wrong *as stated*: circularity applies to
   **model-authored** text; `cited_text` is API-extracted and not circular.
   Should read: "landing model-transcribed text is circular and forbidden;
   landing API-extracted citation spans is not — see the evidence_mode fork."
4. **samples/README.md "It does not test PDF extraction" bullet (:312)** —
   "…`evidence_unverified` therefore never occurs in this suite." False since
   fixture 07, which the same file describes producing exactly that status.
   Also ":310 Six fixtures, at most two inputs each" — seven.
5. **samples/README.md fixture-07 quoted preflight output (:339)** — the quote
   shows three warning lines; the code now prints five **[repro]** (the "NO
   mechanism linking a value to its source" and "model choice is a CORRECTNESS
   decision" lines are missing). Requote.
6. **samples/README.md fixture-07 "Two things this fixture does not prove"
   (:350)** — "it says nothing about whether a real model … will comply rather
   than fabricating a verbatim quote — that needs a live call." The live call
   happened and answered: haiku fabricated `'$30.00'` and landed a wrong value
   `ok` four times. The framing "unproven" is stale; it is now
   **proven-adverse** and should cite the L1 record in SPEC-CHANGES.
7. **transport.py `estimate` docstring (:731)** — "The heuristic errs high on
   purpose." Contradicted eight lines up by `_PDF_TOKENS_PER_KB`'s own comment
   ("KNOWN WRONG for PDFs, and in the dangerous direction"). Until the Part C
   fix lands, the docstring must carry the same caveat — a module that asserts
   a safety property its own constants disclaim is worse than one that says
   "errs high for text, errs low for PDFs."
8. **SPEC-CHANGES.md "Estimator note" (:759)** — "`pricing_is_approximate`
   flags it, but the printed figure is ~20x." Overstated: in the preflight
   path that printed the $1.21, the flag is **False** because `cmd_preflight`
   drops `spec.model` **[repro]** — the flag *would* fire only via
   `from_spec`, which that path doesn't use. Also "~20x" describes the rate
   error only; against actual usage (1,140/75 tokens at haiku rates ≈ $0.002)
   the printed figure was ~600x, dominated by the `max_tokens`-sized output
   term, not the rates. Correct the note when fixing the code (Part C L5.1).
9. **transport.py `_classify_transport_exception` 400 hint (:1240)** — still
   asserts "Common causes … unsupported JSON Schema keyword … or thinking
   disabled above high effort" as a diagnosis. L3's own record shows this
   exact sentence steering the operator wrong. Rephrase per Part C ("the
   harness cannot see which parameter; candidates, most likely first…").
10. **`_MAX_REQUEST_BYTES` / `_MAX_PDF_PAGES_PER_REQUEST` (transport.py:164,
    :168)** — commented as "for preflight refusal rather than a 413 discovered
    mid-population", but both are dead: zero call sites **[repro]**. Either
    wire them into `estimate`/`fits_within` (Part C L5.4) or the comment must
    say "not yet enforced."
11. **CONTRACT.md §"schema.py split" (:71)** — "rejected outright when
    combined with citations" — worth noting this was *correct before L4
    verified it*; no change needed. Listed so the sweep is auditable: the one
    place the docs already knew about the citations incompatibility.

---

## Suggested order

1. **D-1** (`dataclasses.replace` in `map_inputs`) + **L5.1** (`from_spec` in
   `cmd_preflight`) — two one-liners closing demonstrated hash/pricing
   integrity holes; both are second instances of already-documented bug
   classes, which is itself the argument for doing them first.
2. **A3** (media-direct + `min_evidence>0` refusal, fixture 07 update) — makes
   L1's H-dressing structurally impossible and routes the trade through spec
   hash + grant.
3. **Part C L3** (omit `thinking` on non-reasoning models both branches;
   hypothesis-phrased 400 message; capability probe) and **L5.2–4** (rate
   table, page/flat-cap pricing, unpriced-refusal, request-size check).
4. **A1** (cross-field checks) — cheap, and the retry integration pays for
   itself on text paths too.
5. **A2** (cross-model corroboration) — after the grant extension; the only
   mitigation that catches L1's exact instance.
6. **Part B** (`evidence_mode: citations`) — when the first PDF spec exists;
   reserve the vocabulary in CONTRACT now (with sweep items 2–3's rewrites).
7. **A4** (unfalsifiable marking in resolver/review queue) — blocked behind
   REVIEW CV-2/CV-3; do not build against a stub `resolve`.

Doc corrections (Part D items 1–10) can land with whichever code change touches
the same file, except items 1, 4, 5, 6 (pure doc) which should land now.
