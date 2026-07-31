# Fix workflow: FIXES.md A1–A4, Part B, Part C

## Status

| Stage | State |
|---|---|
| 0 — test surface + pins | **LANDED** `454874b`. `verify pins` subcommand; coverage assert found 2 unhashed fields; tripwire proven by injecting D-1 (fixture suite stayed green, pins went red on all 8). |
| 3 — A3 refusal | **LANDED** `b5a2129`. Refusal before dispatch; fixtures 07+08 to `min_evidence: 0`; fixture 09 negative; SYSTEM_PROMPT split per input. Exactly 2 pins moved, as predicted. |
| E2E proof | **LANDED** `950f621` (replay) + `68be520` (live). dlt→duckdb→mapper→gate→dlt. Found 4 bugs reading had missed. |
| 8 — CONTRACT §8 capability gate | **LANDED** `772a499`. |
| 2 — estimator | **LANDED** `2c5545c`. Per-model rates; PDF per-page (old byte heuristic priced a real 2-page PDF at **7 tokens** vs ~15,600 actual); ledger reconciles at the model's rate, so `max_usd` stops at the right point. |
| 4 — A1 cross-field | **LANDED** `2df1539`. Closed vocabulary; retry integration; fixtures 10 (catches) + 11 (pins the blind spot). Exposed a **third** hash-drop site in `with_wire_schema`, found automatically by the coverage check. |
| 5 — A2 corroboration | **LANDED** `0307400`. **L1 is now caught.** Second injected callable; 4 refusals each verified to fire; ledger attribution fixed. |
| 1 — capability probe | **LANDED** `52f0d43`. Live Models API probe, two leaves separated. The API confirmed haiku-4-5 has `thinking` **without** `effort` — the one-boolean defect was real. |
| CV-3 — `cmd_resolve` | **LANDED** `ccec00c`. The review model executes for the first time: human override wins, stale confirmation invalidates. Round-trip checked on every fixture. |
| §7.7 — atomicity | **LANDED** `63a9967`. Characterised, not asserted. Crash-after-success leaves a populated, partly-obsolete table where survivors and orphans look identical. |
| Fixture 07 size | **LANDED** `bdb0347`. 656×272; the misread **survives** — haiku 99.0 vs sonnet 90.0, live. |
| A2 live client | **LANDED** `abbc929`. L1 closed end to end with two real models. |
| 6 — Part B citations | **LANDED**. Fixture `13-citations` lands 4 `api_cited` atoms at a `0.0` unverified ceiling that its twin 08 cannot meet. All seven §6.5 cases pass. The attribution blocker was **withdrawn** — it did not exist; the real question was the circularity ceiling, decided as `API_CITED` in its own status (§6.3). Two unpredicted findings in §6.6. |
| 7 — A4 marking | **LANDED**. `evidence_unfalsifiable` on the effective cell and the provenance sidecar; declared per fixture. CV-2 turned out to be the same defect as the H2 review finding, so both blockers were already closed. |

**Everything in this plan is now landed**, Stage 6 included (§6.6 records what
it cost and what the design did not predict).

**The stated blocker on Stage 6 was wrong and is withdrawn.** Two prior
revisions of this file claimed a citation→field attribution problem: a citation
anchors to a span of *response text* while an evidence atom belongs to a
*field*, with nothing mapping one to the other. Checking the code instead of
re-reading the plan shows the mapping was never needed. The wire schema already
nests `evidence` **under each field** (`schema.py:217-247`), so a quote arrives
already attributed by construction. There is no matching step to design.

That correction also cancels the "one call per field" fallback, which existed
only to buy attribution the schema already provides. It would have multiplied
cost by the field count to solve a solved problem.

The genuine gap is a different one, and narrower: `verify_quote` has no haystack
for media, so media evidence can never be checked (§6.2). Citations supply that
haystack for PDFs. What that leaves open is a **trust** question, not an
attribution one.

Also landed outside the original plan, because reviews found them: the record
CSV round trip (`cmd_resolve`), publication-atomicity characterisation, the
live corroborating client, per-attempt spend pricing, and A4 marking.

How the Fable recommendations get built and, more importantly, how each one is
*proven* rather than asserted. Written before any of it is implemented.

The organising fact: **these fixes are not independent.** Three of them
(A1, A2, A3) add or change spec fields, and every spec field is hashed into
`mapper_spec_id`. A3 additionally forces an edit to fixture 07's spec. So
landing them together makes "which change moved the hash" unanswerable, and a
moved hash silently unbinds every grant and every review. The workflow below is
therefore staged, with a hash-integrity check between stages, not a single pass.

A second organising fact, from this project's own history: **four times a claim
verified by reading failed when run.** Every stage below has a verification step
that executes something. "I read the code and it looks right" is not a stage
exit.

**This plan was itself reviewed before being adopted**, by the same kind of pass
that found D-1 alive at a second site after I had reported that class fixed. The
review returned twelve findings, four of them severe enough to change the plan's
shape; I verified each against the code before accepting it. The four that
mattered:

- Stage 0's proposed tests had **nowhere to run** — there is no test
  infrastructure at all (§0.0);
- Stage 3 breaks **fixture 08 as well as 07**; the plan named only 07 (§3.3);
- Stage 5's corroboration call **cannot be made through the current seam**,
  which takes no model parameter (§5.3);
- Stage 6's parse reuse was wrong — the fence machinery is **CLI-provider-only**,
  and citations fragment the response across blocks (§6).

Two more corrected a claim I had made without checking: `to_canonical()` emits a
fixed key set, so adding a field moves *all* pins unless serialization is
conditional (§0.3); and Stage 2's exit criterion was arithmetically unachievable
by its own scope (§2). Recorded here rather than silently folded in, because the
plan's credibility rests on which parts were checked and which were assumed.

---

## Stage 0 — build the test surface, then instrument (no behaviour change)

Nothing here alters output. It exists so later stages can *detect* the damage
they might do.

**0.0 There is no test infrastructure. This is a real, unplanned prerequisite.**
`experiments/field-mapper/` has no `tests/`, no `pyproject.toml`, no
`pytest.ini`, no `conftest.py`; `.venv-live` contains `anthropic` and nothing
else. The *only* verification mechanism that exists is the fixture-diff CLI
(`__main__.py:896` `_verify_one`, comparing quarantine/status/evidence counts
against `expect.json`). Neither 0.1 nor 0.2 below is fixture-shaped, so neither
has anywhere to run today.

Decision: **add a `verify pins` CLI subcommand rather than introduce pytest.**
Rationale — the harness deliberately runs on a pinned stdlib-only venv
(`anthropic` is the single dependency, added for live calls); making the
regression suite depend on pytest would make the *test* surface heavier than the
*product* surface, and the existing `verify` command already owns the
"compare computed against recorded" idiom. If pytest is wanted later it can wrap
the same functions.

**0.1 Hash pins.** Pin the **bound** `mapper_spec_id` (post-`with_wire_schema`,
post-`harness_version` stamp — the id the grant actually checks, `__main__.py:125`)
for each of the 8 sample specs. Pinning the bare `spec.json` hash instead would
leave `compile_schema` drift invisible to the tripwire, which defeats the point.

Pins update **deliberately, in the commit that moves them, with the reason in
the message.** A pin updated as a reflex is worse than no pin.

**0.2 A spec-field coverage assert.** Walk `dataclasses.fields(MapperSpec)` and
assert every field is either present in `to_canonical()` or named in an explicit
`_HASH_EXCLUDED` set. This is the *generic* form of the D-1 bug class — it fails
when someone adds a field and forgets the canonical form, instead of waiting for
a human to grep. **Both D-1 instances would have been caught at authoring time
by this test.** Must run against a maximally-populated spec so that Stage 4/5's
omit-when-default serialization (see 0.3) doesn't hide a field from it.

**0.3 Version and serialization policy, decided now because later stages depend
on it:**

- `harness_version` **is hashed** (`spec.py:575`). Any `__version__` bump moves
  all 8 pins. Freeze `__version__` across Stages 1–2 so the tripwire means what
  it claims; bump deliberately at a hash-moving stage.
- `to_canonical()` emits a **fixed key set** (`spec.py:563-576`). Adding a field
  the way every existing field is added moves **all 8 pins**, not just the specs
  that declare it. For Stages 4–6 to move only declaring specs, new optional keys
  must be **omitted when default** — a convention with no precedent in the file,
  so it gets established here, in Stage 0, with the coverage assert taught about
  it. `from_dict`'s closed `known` set (`spec.py:608`) also needs extending per
  stage.

**Exit:** `verify pins` green on unmodified `main`; coverage assert passes; 8/8
suite still green.

---

## Stage 1 — Part C, L3: capability handling (no spec-hash impact)

Deliberately first among the behaviour changes because it touches **no spec
field**, so the Stage-0 hash pins must not move. If they move, the change was
not what I thought it was — a free correctness signal.

**1.1 Live capability probe** behind the provider seam. `AnthropicProvider`
gains `capabilities(model)`; `Client` resolves once per run, caches, prefers the
API's answer over `_REASONING_CONTROL_MODELS`, and records a **ledger note when
the table and the API disagree**. The table stays as the no-network fallback —
`preflight` and dry-run must work with no SDK.

Two structural defects this fixes, both from FIXES Part C:
- staleness (an unnamed future family is silently degraded forever);
- bit conflation (adaptive-thinking and `effort` are separate capability leaves;
  Opus 4.5 has `effort` without adaptive thinking, and one boolean cannot say
  that).

**1.2 Hypothesis-phrased 400 handler.** Replace the confident
"Common causes: …" diagnosis — which steered wrong in the one live incident —
with: what is mechanically known, then ranked *labelled* hypotheses, then an
opt-in `FIELD_MAPPER_DEBUG_400=1` that prints the SDK's own message **to stderr
only**, never to the ledger or `error_detail`. The redaction policy is right for
durable surfaces; it is also what forced the harness to guess. An ephemeral
operator-chosen print resolves that without weakening the ledger contract.

**1.3 Scope `_validate_thinking_effort_pairing`** to models that actually emit
the controls.

**Verification — this is the stage that most needs live execution:**
- offline: capability probe mocked both ways (agrees / disagrees), assert the
  ledger note appears only on disagreement;
- **live, with the real key: a haiku call must now succeed** where it previously
  400'd. That is the whole point of the stage and it cannot be proven offline.
  The pre-4.6 `thinking: {"type": "disabled"}` branch fix (already landed) has
  *never been live-verified* — this stage is where that debt gets paid.

**Exit:** Stage-0 hash pins unmoved (proves no spec-surface leak); one live
haiku call green; suite 8/8.

---

## Stage 2 — Part C, L5: the cost estimator

Also no spec-hash impact. Four defects, per FIXES:

- **2.1** per-model rate table (opus $5/$25, sonnet $3/$15, haiku-4-5 $1/$5,
  fable $10/$50), unknown model priced at the **most expensive known rate** plus
  `pricing_is_approximate` — errs high without refusing;
- **2.2** PDF priced **per page** via a stdlib `/Type /Page` byte scan at
  `pages × (3000 + 4800)` tokens; images at a flat 4,784 (documented per-image
  cap). Delete `_PDF_TOKENS_PER_KB`. Byte pricing errs *low*, violating the
  estimator's one stated principle;
- **2.3** unpriceable artifact (url / file_id / unscannable PDF) becomes a
  `fits_within` breach unless `--allow-unpriced`. Today the gate waves through
  precisely the thing it cannot measure;
- **2.4** enforce `_MAX_REQUEST_BYTES` at preflight (`ceil(bytes × 4/3)` + text)
  — currently a constant that looks like a guard and is not one.

Relabel the printed number **"worst-case bound"**, not "spend": with
`per_call_output = max_tokens × retries` it is already a ceiling, and the live
run showed 16,000 estimated against 75 actual output tokens — the `max_tokens`
term, not the rates, was the single largest error factor (~600x, not the ~20x
SPEC-CHANGES claims).

**Verification:** unit tests per rate row; an unpriced-refusal test; a PDF
page-scan test against fixture 08's real 2-page PDF (known answer: 2) **plus a
compressed-PDF case**. The 1,870-byte fixture is hand-built with no
`FlateDecode` and no object streams, so a raw `/Type /Page` scan finds it
trivially; realistic PDFs store page objects in compressed object streams where
the scan finds **zero**. Without the compressed case the test cannot tell a
working scanner from one that is broken on every real input and silently routes
everything to unpriced-refusal. Expected outcome for the compressed case:
unpriced, not a wrong count.

**Exit criterion — corrected.** The plan originally demanded the printed bound
land "within one order of magnitude of the ledger's actual." That is
unachievable by this stage's own scope: `estimate()` sets
`per_call_output = expected_output_tokens or cfg.max_tokens` (`transport.py:790`)
with `max_tokens=16_000`, times `calls_per_cell = 1 + max_validation_retries`.
Stage 2 fixes *rates* (≤5x for haiku) and relabels the number; it deliberately
leaves the `max_tokens` term, which is itself the ~600x dominant error. After
this stage the bound is still ~2 orders above a 75-output-token actual — **by
design, because it is a ceiling.**

So the exit check is: **input-token and rate arithmetic within 10x of actual**,
and the output term explicitly labelled worst-case. Passing a realistic
`expected_output_tokens` is a separate change, noted here and not smuggled in.

**Exit:** hash pins unmoved; estimate-vs-actual gap, decomposed into rate error
vs `max_tokens` error, recorded in SPEC-CHANGES.

---

## Stage 3 — A3: refuse unfalsifiable evidence obligations (FIRST hash-moving stage)

From here on, every stage moves a spec hash. One stage at a time, exit checked.

**3.1** In `map_inputs`, after quarantine and **before any dispatch**: if any
surviving input `is_media_direct` and any field declares `min_evidence > 0`,
raise `SpecError`. Systemic, blocks, costs nothing — the model can *never*
produce a checkable atom on this path, so retrying is spending money to
rediscover a static fact.

Not at construction time (an unbuildable spec is un-inspectable; `preflight`
must still run and explain). Not per-cell (that burns retries on an
unsatisfiable constraint).

**3.2** The error text must name the whole consequence chain, because that chain
*is* the fix: set `min_evidence: 0` → the blindness is declared and hashed →
`mapper_spec_id` changes → every prior review correctly unbinds → the grant
stops matching → **a human re-consents to a spec that admits it runs
evidence-blind.** The consent gate demonstrably fires live (L1 §1), so this is
enforcement that already works, pointed at the right thing.

**3.3 TWO fixtures need editing, not one.** Fixture 07 declares
`min_evidence: 1` on both fields; **fixture 08 declares it on all four**, with
`accepts_media: ["application/pdf"]` and media-direct inputs. Both fixtures
demand evidence their path cannot check, and the refusal fires on both — so
without editing 08 the suite goes red on it (its `expect.json` declares no
`blocks`). Set both to 0, re-derive both grants, **update two hash pins
deliberately with the reason in the commit message.**

Note the knock-on: this weakens Stage 6's premise, which treated fixture 08 as
the evidence-bearing PDF spec. After Stage 3 it is evidence-blind, and Stage 6's
citations mode is what would restore an evidence obligation it can actually
discharge.

**3.4** Add a negative fixture asserting the refusal fires. This is expressible
today with no new infrastructure: `SpecError` is a `SystemicError`
(`errors.py:166`), which `_verify_one` already catches under `expect.blocks`
(`__main__.py:953`).

**3.5 Aim this at `SYSTEM_PROMPT`, not the fixture instruction.** Fixture 07's
instruction *already* asks for region descriptions and forbids invented
quotations. The verbatim-quote pressure comes from the harness system prompt
(`mapper.py:82`: "cite verbatim spans … Quote exactly — never paraphrase"),
which contradicts every media-direct instruction. The live haiku fabrication is
evidence the per-spec instruction alone does not win against it. Fix: a
conditional evidence paragraph on media-direct dispatch. This moves
`prompt_hash`, **not** `mapper_spec_id` — so it does not add pin churn.

**3.6 Blast radius, stated as a decision.** The predicate "any surviving input
is media-direct AND any field has `min_evidence > 0`" blocks the **whole run**
even when other inputs carry `landed_text` and could legitimately satisfy the
obligation. Inherited from FIXES A3. Accepted deliberately: a per-input
downgrade would make the same spec mean "evidence required" for some rows and
"evidence waived" for others, with nothing in the spec hash recording which — a
worse failure than an over-broad refusal that a human resolves by declaring
intent. Recorded here so it is a choice rather than an oversight.

**Verification:** negative fixture blocks with the expected message; fixtures 07
and 08 green under `min_evidence: 0`; **exactly two hash pins moved, and they
are 07's and 08's.** That last check is the stage's real exit criterion.

---

## Stage 4 — A1: cross-field structural checks

Closed vocabulary, no expression language:

```json
"cross_field_checks": [
  {"kind": "product_equals", "factors": ["quantity", "unit_price"],
   "target": "total_usd", "tolerance": 0.005}
]
```

New `check_cross_field` in `validate.py`, evaluated in `_validate_response`
after the per-field pass, violation attached to `target`, flowing into the
**existing retry loop** so the correction turn says
"quantity=2 × unit_price=45.00 ≠ total_usd=30.0". Exhaustion →
`validation_failed`, value discarded, exactly like a range violation. Tolerance
is for float representation only, never fuzzy string matching.

**Honest scope, kept in the docs:** catches internally-inconsistent misreads;
does **not** catch *consistent* misreads, artifacts with no internal redundancy,
or non-numeric fields. The real cost is authorial — the spec must extract the
redundant fields for the check to have anything to bite on.

**Verification:** a fixture whose recorded response is arithmetically
inconsistent, asserting retry-then-`validation_failed`; a consistent-misread
fixture asserting the check **does not** fire (pins the documented blind spot so
it can't be quietly overclaimed later); hash pins move only for specs that
declare the new key.

---

## Stage 5 — A2: cross-model corroboration

The only mitigation that catches L1's exact instance: sonnet and a direct read
both return $90.00; haiku stably returns $30.00.

**5.1** `"corroboration": {"model": "..."}`, legal only when `accepts_media` is
non-empty. Per media-direct **input**, not per cell. After the primary
validates, one additional call with a `TransportConfig` derived from the
corroboration model — capability gating applies independently, which is why the
knob must be a model id and not a config copy.

**5.2** Compare per-field typed values: strings after `normalize_text`, numbers
exact, bools/enums exact. **No tolerance, no similarity** — fuzz here reopens
the hole the substring check refuses to open.

- agreement → cell stays `ok`, evidence stays `evidence_unverified`.
  **Agreement is corroboration, not verification; statuses must not upgrade.**
- disagreement → `validation_failed`, both models and both values named, value
  **discarded** (one is wrong, we don't know which; landing either is a coin
  flip), `needs_review=True`.

**5.3 The injected seam admits exactly one model — this is the stage's real
work, and the plan originally missed it.** `map_inputs` receives one
`call(item=, spec=, wire_schema=, violations=)` (`mapper.py:519`) closed over a
single `Client` with a single `TransportConfig` built by the caller
(`__main__.py:399`). The mapper layer *cannot* construct "a `TransportConfig`
derived from the corroboration model" — CONTRACT deliberately keeps
`transport.Client` out of its reach. So A2 requires changing the seam contract:
a second injected callable (preferred — it keeps the one-model-per-callable
property and needs no new import in `mapper.py`), or a model parameter on the
existing one.

Three consequences, all unmentioned in the source recommendation:
- `RecordedPlayer` / `recorded.json` must be extended to replay corroborator
  answers (`__main__.py:335`), or no fixture can exercise this offline;
- the ledger hardcodes `request_params={"model": spec.model, "effort": spec.effort}`
  (`mapper.py:924`), which would **misattribute every corroboration attempt to
  the primary model** — precisely the audit-trail corruption the `provider` /
  `provider_notes` fields were added to prevent;
- `estimate()` / `calls_per_cell` must count the extra call.

**5.4** Grant gains `corroboration_model`; a corroborating run under a grant
that doesn't name the second model **must refuse**, same as the model-mismatch
refusal that already works.

**5.5 Cardinality is not a problem here — checked, and worth recording as
checked.** One `MapperInput` produces exactly one row (`mapper.py:344`; fixture
01 is 2 inputs at `expected_per_input: 1`), so the corroborator answers the same
fixed per-field schema and field-by-field comparison is well-defined. The
genuinely unspecified case is **value-vs-`ABSENT_SENTINEL` disagreement** — one
model returns a value, the other says absent. Decision: treat as disagreement
(`validation_failed`, value discarded), since "one model could not find what the
other confidently read" is exactly the situation a human should adjudicate.

**Verification — the one stage with a decisive live test available:**
re-run fixture 07 live with haiku primary + sonnet corroborator. Known ground
truth: haiku says $30.00, sonnet says $90.00. **The cell must land
`validation_failed`, not `ok`.** This converts L1 from an open finding into a
regression test. Offline: agreement path, disagreement path, grant-refusal path.

---

## Stage 6 — Part B: `evidence_mode: citations`

Build when a PDF spec exists; fixture 08 now means one does.

`"evidence_mode": "structured" | "citations"`, the latter legal only for
media-direct `application/pdf`. Request carries `citations: {enabled: true}` and
**no `output_config.format`** (the two are mutually exclusive — 400). Schema
requested in prose, validated post hoc against the compiled schema.
Non-conforming → `SCHEMA_REJECT`, burns a retry, can never land.

**The parse work is larger than "reuse the fence machinery" — corrected.**
`_FENCE` (`providers.py:68`) is used *only* inside `ClaudeCliProvider._to_response`
(`providers.py:374`). `AnthropicProvider.dispatch` returns the raw SDK message
(`providers.py:164`) and the Anthropic-path parse is
`transport._interpret` → `json.loads(_first_text_block(response))`
(`transport.py:1166`), where `_first_text_block` returns **only the first** text
block (`transport.py:1290`). With citations enabled the API splits output into
**multiple** text blocks — cited blocks carry `citations` arrays — so the JSON
body is fragmented and first-block parsing fails outright.

Stage 6 therefore needs two things the plan did not name:
1. **block concatenation** plus fence/JSON search hoisted into `_interpret` or a
   shared helper, so both providers use one parse path;
2. a **citations carrier on `CallResult`** (`transport.py:749` has `parsed` and
   nothing else) to get `cited_text` / `page_location` down to
   `mapper._evidence_for`.

A third item stood here — a citation→field attribution design — and it was
wrong. See §6.1. It is struck rather than deleted because the plan's value
depends on which claims were checked and which were assumed, and this one was
assumed across two revisions.

### 6.1 The attribution blocker, withdrawn

The claim was that a citation anchors to a span of response text while an
evidence atom belongs to a field, with nothing mapping one to the other.

The compiled wire schema (`schema.py:214-247`) emits, per field:

```json
{"value": <typed | absent-sentinel>,
 "evidence": [{"quote": "...", "source_field_name": "..."}]}
```

`evidence` is **nested inside the field's own object**. A quote is therefore
bound to its field by position in the JSON tree, before any citation exists.
Enabling citations does not move the values out of that shape — it fragments the
*transport* of the text across blocks (item 1 above, still real) and attaches
`cited_text` to those blocks. The field binding is unaffected.

So the attribution work is zero, and the per-field-call fallback that was
proposed to buy attribution is cancelled: it would have multiplied cost by the
field count to solve a problem the schema already solved.

**Why the error survived two revisions:** the plan reasoned about the Anthropic
citations API in the abstract, where citations do anchor to response spans,
without checking what this harness asks the model to emit. The general fact was
true; its application here was not.

### 6.2 The real gap: `verify_quote` has no haystack for media

`verify_quote` (`validate.py:410-451`) checks a quote as a substring of
`landed_text` and returns one of three statuses. Its `evidence_unverified`
branch fires on exactly one condition: **`landed_text is None`.**

For a media input that is always the case. `MapperInput.is_media_direct`
(`mapper.py:195`) is `bool(self.media) and self.landed_text is None` — there is
no canonical text of a PNG to check a quote against. Every media quote returns
`evidence_unverified`, which is what Stage 7's `evidence_unfalsifiable` now
marks.

This reframes fixtures 07 and 08. They are not unfalsifiable because attribution
is unsolved; they are unfalsifiable because **the haystack does not exist.**

Citations supply that missing haystack for PDFs: `cited_text` is extracted from
the document **by the API**, not authored by the model. That is a second party's
reading of the bytes.

### 6.3 The open decision: does `cited_text` count as verification?

It arrives in the same response as the value. `verify_quote`'s docstring bans
precisely this:

> it makes it structurally impossible to validate a quote against text the model
> returned in the same response. That check is circular and proves nothing.

Citations are extractive rather than generative, so the circularity is weaker
than the case that docstring guards — but it is **not** the independent landed
model the contract requires. Both readings are defensible:

- **Collapse into `verified`** — simplest, and the extraction is genuinely not
  the model's authorship.
- **Its own status** — keeps the audit meaning of `verified` intact.

**Decision: its own status, `API_CITED`.** `verified` has one contract — *the
harness ran a substring check it can re-run offline from `text_hash` + offsets*.
An API citation cannot be re-run offline; re-checking it means trusting the same
response again. Collapsing the two would let a provider-side extraction clear
the same gate as a check against independently landed text, and that is the
distinction the two-stage design exists to hold.

Consequences, which are the point of choosing this way:

- counts as verified-equivalent **for gating** — it does not inflate
  `unverified_share`, and it satisfies `min_evidence_per_ok_cell`;
- **not** `verified` in the audit trail, so a reviewer can always ask "which of
  these did we check ourselves?" and get an answer;
- `evidence_unfalsifiable` (Stage 7) must stay **false** for an `api_cited`
  atom. The A4 predicate is `all(atom is EVIDENCE_UNVERIFIED)`, so an enum
  member that is neither `EVIDENCE_UNVERIFIED` nor `VERIFIED` gets this right
  with no edit — but it must be **asserted by test**, not assumed, since a later
  refactor to `!= VERIFIED` would silently invert it.

**New vocabulary:** `API_CITED = "api_cited"`, landing in **two places, not
one**. Verified by execution, and the shape is worse than previously recorded:

- `records.py:108` — `VerifyStatus(_LandedEnum)`, members `VERIFIED`,
  `EVIDENCE_UNVERIFIED`, `VERIFY_FAILED`.
- `validate.py:71` — a **second, unrelated class also named `VerifyStatus`**,
  a plain class of string constants plus an `ALL` frozenset, with members
  `VERIFIED`, `UNVERIFIED`, `FAILED`.

Same class name, same string *values*, **different member names**. They are
bridged only by the string: `mapper._evidence_for` builds the records enum from
the validate constant, so a member added to one side alone raises `ValueError:
'api_cited' is not a valid VerifyStatus` at atom construction — confirmed by
running it. That failure is loud, which is the good case; the trap is that
`validate.VerifyStatus.API_CITED` and `records.VerifyStatus.API_CITED` look
interchangeable at a call site and are not the same object.

Add to both, and add `API_CITED` to `validate.ALL` — omitting it there is the
silent half of the failure, since `ALL` is what gates landed vocabulary.

`extractor` = `anthropic-api-citations` + the `anthropic-version` date, so a
change in extraction behaviour is attributable after the fact.

`VerifyStatus` subclasses `_LandedEnum` (`records.py:50`) — its values are
**persisted CSV vocabulary**, gated by `all_values()`. Adding a member is a data
format change: rows written after it can no longer be read by a build without
it. Worth stating in `SPEC-CHANGES.md`; it does not move `mapper_spec_id`, since
verify status is landed data rather than spec.

**The trade:** schema-guaranteed parse vs fabrication-proof evidence. For this
harness evidence is the scarcer good — the wire schema was never the load-
bearing enforcement (`validate.py` re-checks everything after parse), so losing
it costs retries, never correctness. What citations uniquely buy — `cited_text`
extracted **by the API, never authored by the model** — is the property the
entire two-stage design was built to reconstruct.

### 6.4 Scope limit: this closes the PDF path, not the media path

Citations apply to document blocks (PDF, plain text) — **not images**. Fixtures
07 and 08 are PNGs. The cells this harness currently cannot falsify are exactly
the ones citations **cannot** fix.

Stating it plainly because the opposite is the natural assumption: Stage 6 does
not retire `evidence_unfalsifiable`. It gives PDF specs a path to evidence that
is checkable by someone other than the model, and leaves image specs where they
are — which is why A3 (refuse unfalsifiable obligations) and A4 (mark them) stay
load-bearing after Stage 6 lands.

### 6.5 Verification

Reading proves nothing here; four times in this project a read-verified claim
failed when run. Each of these must execute:

1. **Live PDF call, citations on** — assert `cited_text` returns with
   `page_location`, and lands `api_cited`. Uses the existing throwaway key path.
2. **Multi-block parse** — assert the concatenating parser recovers the JSON
   object when the API splits it across cited blocks. Must be proven to *fail*
   against the current `_first_text_block` (§6, item 1), or it is not testing
   anything.
3. **Image spec rejection** — `evidence_mode: citations` on a media/PNG spec
   refuses at spec validation, not at dispatch and not silently degraded.
4. **Vocabulary two-place landing** — a test that constructs an atom with
   `api_cited`; it raises today, passes only when both `validate.py` and
   `records.py` carry it. This is the pin for the class of bug the plan already
   predicts.
5. **A4 interaction** — an `api_cited` atom must yield
   `evidence_unfalsifiable = false`. Asserted, not assumed (§6.3).
6. **Gating arithmetic** — an `api_cited` atom satisfies
   `min_evidence_per_ok_cell` and does not raise `unverified_share`.
7. **Pins** — `verify pins` stays 12/12. Verify status is landed data, not spec,
   so `mapper_spec_id` must not move. `evidence_mode` **does** move it when set,
   which is why it must be omitted from `to_canonical()` at its default (§0.3) —
   the fourth appearance of the omit-when-default trap, which has shipped as a
   bug three times.

### 6.6 Outcome — all seven pass; two things the design did not predict

Stage 6 is **built and verified**. Fixture `13-citations` lands four `api_cited`
atoms at `max_unverified_share: 0.0` — a ceiling fixture 08 cannot meet with the
same PDF, the same fields, and the same quotes. That pair is the proof, and
`pins` now records 13 hashes with 13 deliberately distinct from 08.

Two findings cost real debugging time and are worth stating, because neither is
visible from reading the code.

**1. Asking for JSON suppresses citations entirely.** Citations attach to
narrative text blocks. `_instruction_with_prose_schema` originally said "Return
ONLY a JSON object … with no prose before or after it", which is exactly the
instruction that leaves the API nothing to cite. Measured on the fixture PDF,
one call each:

    json only        blocks=1   cites=0
    prose then json  blocks=10  cites=4

The mode was fully wired and returned **zero** citations, with no error anywhere
— every atom simply stayed `evidence_unverified` and the build blocked. The fix
is to ask for prose *then* JSON; the prose is load-bearing, not decoration, and
deleting it silently reverts `citations` to `structured` behaviour. `pins` now
carries a parser invariant so the recovery of the JSON tail cannot regress
quietly (a break there presents as "the model stopped complying", which is the
wrong diagnosis).

**2. The upgrade had to land in two places, and the first one was the wrong
one.** `_evidence_for` computes the statuses that are *displayed and landed*;
`_validate_response` computes the ones `evaluate_coverage` *gates on*. Upgrading
only the former produced a run whose sidecar showed `api_cited 4` while the gate
still blocked on `evidence_unverified 100%` — the audit trail and the decision
disagreeing about the same atoms. Both now call one `_verify_atom` helper. A
status that governs a decision and a status shown to a human must come from the
same rule, and the duplicated-rule shape is what let them drift.

Both findings are the same underlying shape as the two-`VerifyStatus`-class trap
this document already warns about: a rule expressed in two places, where the
copies are only bridged by a string.

---

## Stage 7 — A4: unfalsifiable marking (LANDED — header kept for history)

One boolean `evidence_unfalsifiable` on the effective cell, populated by
`resolve()` from data the `Resolution` bundle already holds; review queue renders
those rows with the artifact and a banner.

**Blocked behind REVIEW CV-3 (`cmd_resolve` is a stub) and CV-2 (review ingress
ordinal bug).** A marking column on a path no reviewer can exercise is
decoration. Listed here so it is not forgotten, not so it is built next.

Worth stating what already works: the media digest is in `snapshot_projection`,
so **swapping the artifact already unbinds the confirmation** as
`input_changed`. The undetectable case is only "same artifact, stably wrong
model" — which is A2's job, not binding's.

---

## Explicitly rejected (recorded so they are not re-proposed)

- **Self-consistency across N same-model calls.** L1 is *defined* by stability —
  four consecutive identical wrong answers. Same-model resampling is blind to it
  by construction and costs k×.
- **Same-model transcribe-then-extract.** The anchor is the same model's
  reading; haiku's transcript would say `$30.00` and the substring check would
  *certify* the misread. Catches fabrication between stages, not misreading.

---

## What remains broken after all of this

A stable, **correlated-across-models** misread of an artifact with no internal
redundancy still lands `ok` — declared `min_evidence: 0`, unfalsifiable-marked,
consented to. That residual is irreducible without a text layer. It is what
"evidence-blind" means. These fixes make the harness *say* it rather than
pretend otherwise.

Separately unaddressed and **blocking real transform integration** (not fixed by
any stage above):

1. `cmd_resolve` is a stub — the durable-review half has never executed;
2. no transform integration exists; every dlt claim in the mockup is read, not
   observed;
3. publication is not atomic across two `pipeline.run` calls, and the
   fault-injection test CONTRACT §7.7 requires does not exist;
4. where `mapper_reviews` physically lives is undecided (design §15 Q5).

---

## Verification harness (applies to every stage)

1. `python3 -m field_mapper verify samples` — must stay green. Count grows:
   8 today → 9 after Stage 3's negative fixture → **11** after Stage 4 (which
   needs *two*: an arithmetically-inconsistent case and a consistent-misread
   case pinning the documented blind spot) → more from Stage 5's
   agreement/disagreement/grant-refusal paths. The count is not the check; the
   check is that every fixture's `expect.json` still matches.
2. **Hash pins** (`verify pins`, built in Stage 0) — must move *only* in stages
   that intend to move them, and only for the specs that changed. Reviewed as
   part of the diff, never updated reflexively.
3. **Live call** at Stages 1, 2, and 5 with the real key. Stage 5's is the
   decisive one: it turns L1 into a regression test.
4. **A Fable review pass on the finished diff**, since a Fable pass is what
   found D-1 alive at a second site after I had reported that class fixed.

## Order and why

**Stage 0 is a hard prerequisite, not instrumentation-as-nicety** — it builds
the only mechanism (`verify pins`) by which any later stage can prove it changed
what it claimed. Its cost was invisible in the first draft of this plan because
the plan assumed test infrastructure that does not exist.

Stages 1–2 next: no hash impact, so the pins act as a tripwire proving the
change was as scoped — provided `__version__` stays frozen across them (§0.3),
since `harness_version` is hashed. Stage 3 then makes L1's *dressing*
structurally impossible; it is the cheapest hash-moving change, so the pin
machinery gets exercised on a case with a known expected answer (exactly two
pins move). Stages 4–5 attack the wrong value itself, cheap-deterministic before
expensive-probabilistic. Stage 6 is independent; it was held back on a blocker
that turned out not to exist (§6.1), and is now designed but unbuilt. Stage 7
does not start.

*(Stage 7 subsequently landed, Stage 6's blocker was withdrawn on inspection,
and Stage 6 itself is now built and verified — §6.6. All of it is left as
written above: the ordering argument is the record of what was believed at
planning time, and the corrections are more useful visible than silently folded
in. Worth noting the last line aged badly — Stage 6 was the cheapest stage to
finish once the blocker evaporated, and cutting it would have cost the only
evidence path that works on a PDF.)*

Stage 5 is where the money is: it is the only stage whose verification converts
L1 from an open finding into a regression test, because ground truth is already
known (haiku $30.00, sonnet $90.00, correct answer $90.00). If effort has to be
cut, cut Stage 6 before Stage 5.
