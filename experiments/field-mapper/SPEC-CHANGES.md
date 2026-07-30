# Proposed spec changes

Four extensions, derived from [GENERALITY.md](GENERALITY.md)'s 13-scenario stress
test. Ordered by what unblocks the most with the least machinery.

Each section states the change, the mechanism, what it unlocks, and what it costs.
Where an extension depends on a [REVIEW.md](REVIEW.md) defect being fixed first,
that is called out — two of them promote an existing "high" finding to a blocker.

**Extension 1 is implemented** (see [Implementation status](#implementation-status)
at the bottom). Extensions 2–4 are proposals.

| # | Extension | Unlocks | Depends on |
|---|---|---|---|
| 1 | Media inputs (any modality) — **LANDED** | Image/PDF/audio-blob specs; kills the `pdf`-shaped API | — |
| 2 | Row-array output + `identity_source: output` | Multi-row extraction from any medium | REVIEW H-2 |
| 3 | Pinned landing | Any staged extraction | Extension 1 |
| 4 | `snapshot_scope: row \| population` | Append-stable reviews; partitioned runs | — |

---

## 1. Media inputs — the harness accepts any modality

### The problem

The media path is `pdf`-shaped at every layer, and unreachable from the mapper.

`transport.py:578` hardcodes `application/pdf` inside a function named
`build_pdf_content_block`, emitting `"type": "document"`. `build_user_content`
takes `pdf_inputs: Sequence[bytes]`. And `mapper.py` contains **zero**
occurrences of `pdf` — `MapperInput` has no media field at all, and the dispatch
loop passes only `text_inputs=[item.landed_text]` (`mapper.py:415`).

So `build_pdf_content_block` is **dead code**: reachable by calling
`transport.py` directly, never through `map_inputs`. No fixture exercises it —
`samples/` contains no PDF, and fixture 02 ("text-extraction") starts from
already-landed text.

Two consequences. The send path was built and orphaned, so its correctness is
unproven. And the naming makes PDF look like the domain when it is one codec:
an image, a scanned page, a spreadsheet screenshot, and an audio blob are the
same problem.

### Why generalizing is the right move, not scope creep

GENERALITY.md S5 proved the principle from the other end: **modality is
irrelevant to the evidence contract once text is landed.** An ASR transcript
substring-verifies exactly as mechanically as extracted PDF text —
`extractor`/`extractor_version` carry the producer identity, `page` serves as an
utterance index. Stage 2 is modality-blind.

The corollary: if stage 2 is modality-blind, modality is **entirely** a stage-1
concern, and stage 1 should accept any medium. PDF is not special.

### The change

**Transport — a media block abstraction.** The API distinguishes block *types*,
not just media types: a PDF is `{"type": "document"}`, an image is
`{"type": "image"}`. This is not a `media_type` enum widening.

```python
@dataclass(frozen=True)
class MediaInput:
    """One non-text source artifact handed to the model.

    NEVER the evidence substring surface — see MapperInput.media below.
    """
    media_type: str                      # "application/pdf", "image/png", ...
    data: bytes | None = None            # base64 path
    url: str | None = None               # url path
    file_id: str | None = None           # Files API path
    label: str | None = None             # attribution when several are supplied
```

As built, `kind` is a **derived property** rather than a declared field, read from
the `SUPPORTED_MEDIA_TYPES` table. Declaring it separately would have permitted
`kind="document"` with `media_type="image/png"`, a disagreement needing its own
validation; deriving it makes the disagreement unrepresentable.

`build_media_content_block(m)` dispatches on `kind` and on which of
`data`/`url`/`file_id` is set. `build_user_content(media_inputs=...)` replaces
`pdf_inputs`. `build_pdf_content_block` becomes a thin constructor kept for its
existing callers.

Validation belongs here: exactly one source form set; `kind`/`media_type`
agreement (`image/*` must not arrive as `kind="document"`); a supported-media-type
allowlist, since an unsupported type is a wasted call plus a `SCHEMA_REJECT`.

**The three source forms are a cost decision, not a detail.** A 40-page PDF
re-sent as base64 on every validation retry is billed every time; `file_id`
uploads once and is referenced. The preflight estimator (`pdf_sizes_bytes`)
should generalize to `media_sizes_bytes` and account for retry multiplication.

**`MapperInput` — carry media, without touching `landed_text`.**

```python
media: Sequence[MediaInput] = ()
```

`MapperInput`'s docstring already states that `landed_text` is "never a PDF blob,
never text the model returned in the same response, both of which make the check
circular." That invariant is load-bearing and this change must not weaken it:
**`media` and `landed_text` are separate fields with separate roles.** `media`
goes to the model; `landed_text` is the substring haystack. A `MapperInput` may
carry both (a PDF plus its previously-landed text), either alone, or neither.

`snapshot_projection` must include a **stable digest** of each media input —
content hash for `data`, the URL for `url`, the id for `file_id` — never the
bytes. Media is part of what was read, so changing the image must unbind reviews.
Omitting it would let a swapped image silently inherit confirmations.

**Spec — declare accepted media, derive the evidence ceiling.**

```python
accepts_media: tuple[str, ...] = ()   # media types this mapper accepts
```

The important half is not the declaration but the derivation. A spec whose input
is media-direct has **no substring surface**:

| Input | Substring surface | Reachable `verify_status` |
|---|---|---|
| landed text | yes | `verified` |
| PDF direct | no | `evidence_unverified` only |
| image direct | no | `evidence_unverified` only |
| media → landed text (staged) | yes | `verified` |

GENERALITY.md S6 caught the trap: a screenshot spec must set
`max_unverified_share: 1.0`, which makes §4's strongest ceiling decorative. So
the harness must **derive** this rather than trust a declaration — at preflight,
a media-direct spec reports "this mapper runs evidence-blind; `verified` is
unreachable for N of M fields."

As built, a media-direct spec declaring `max_unverified_share < 1.0` is **not** a
construction-time `SpecError` (as this section originally proposed) but a preflight
warning naming the exact consequence: the run will block on the unverified
ceiling. Rejecting at construction would make the spec object unbuildable, which
also makes it un-inspectable — the author could not run `preflight` to see *why*.
The blocking still happens, at the gate, where the other §4 ceilings block.

### What it unlocks

Image inputs (S6), audio blobs, any future modality. Removes the PDF-specific
vocabulary that made a general problem look narrow.

### What it does not solve

Multi-row output from one medium (extension 2) and nondeterministic
re-extraction (extension 3). Media-direct scoring of a *single* image into a
*single* row works with extension 1 alone.

### Cost

Small and mechanical: ~40 lines in `transport.py`, one field on `MapperInput`,
threading at `mapper.py:415`, one spec field, one preflight check. The
snapshot-digest change touches review binding, so it needs its own fixture: swap
the image, confirm reviews unbind as `input_changed`.

---

## 2. Row-array output + `identity_source: output`

### The problem

`map_inputs` derives `target_row_key` from `item.identity` **before** the call
(`mapper.py:401`), and `compile_schema` emits a single fixed-property object with
`additionalProperties: false` (`schema.py:280`). **The model can never mint a
row.** One input in → exactly one row out, always.

This is why all three GENERALITY.md BREAKS are one axis: invoice line items,
résumé employment stints, PDF page transcription. Each needs rows the model
discovers.

The sharpest part is an internal contradiction. `spec.py` already carries
vocabulary for exactly this case — `source_locators` (`spec.py:207`, whose comment
is about "two employment records at the same employer"), `ordinal_suffix`,
duplicate-disambiguation policy — and the dispatch loop cannot execute any of it.
The spec language is more general than the implementation.

### The change

**A second schema-compile mode.** When the spec declares
`identity_source: output`, `compile_schema` emits:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["rows"],
  "properties": {
    "rows": {
      "type": "array",
      "items": { /* the current single-row object, plus identity fields
                    as ordinary wire properties */ }
    }
  }
}
```

Identity fields become ordinary declared wire fields. `items` is already in
`WIRE_SUPPORTED_KEYWORDS`, so no wire-schema groundwork is needed.

**Key derivation from response values.** `derive_target_row_key` already hashes
values rather than positions, so this stays content-derived: a reorder of the
response does not rename rows, which is exactly the property §3 demanded.
Cardinality asserts move from "one row per input" to the spec's declared
`min_rows`/`max_rows`/`expected_per_input`, which is what those fields were for.

**Duplicate policy becomes reachable.** `ordinal_suffix` and `source_locators`
finally have a code path: two stints at the same employer collide on key, and the
declared policy disambiguates.

### The trust model changes — say so explicitly

Under `identity_source: input`, a row key is adapter-supplied and therefore
trustworthy. Under `identity_source: output`, it is model-supplied. Two new
failure modes:

- **A hallucinated identity value mints a phantom row.** Substring evidence on
  *other* fields cannot catch it — the evidence proves those fields' quotes
  occur, not that the row's subject exists.
- **A transcription variant orphans reviews via a new key rather than a stale
  one.** "Acme Corp" vs "Acme Corp." are different keys, so yesterday's
  confirmation attaches to a row that no longer exists.

That second one **promotes REVIEW.md H-2 from high to blocker.** H-2 is: reviews
whose row key vanished are neither applied nor surfaced as stale, because the
resolver iterates only current proposals. Under `identity_source: input`,
vanished-key is a corner case. Under `identity_source: output` it is the
**common** invalidation path, and silently dropping it means human review work
disappears with no signal. CONTRACT §6.7 already forbids that.

So extension 2 must not ship before H-2 is fixed. The resolver must iterate the
union of proposal keys and review keys, emitting `stale_review_rows` with a
`row_vanished` reason.

### What it unlocks

S2 (invoice line items), S3 (résumé stints — the whiteboard extraction case),
S4a (PDF page rows), the clean form of S8 (population-batch duplicate
detection), and the stronger form of S12. Four to five scenarios, including all
three BREAKS.

### Cost

The largest of the four. Second compile mode, a key-derivation path, duplicate
enforcement over emitted rows, cardinality assert rework, H-2 fixed first.
Fixtures: a 3-line-item invoice; a stint collision resolved by `ordinal_suffix`;
a vanished-key review surfacing as `row_vanished`.

---

## 3. Pinned landing for extraction-class mappers

### The problem

Stage-2 `input_snapshot_id` includes `normalize_text(landed_text)` — deliberately,
per `snapshot_projection`'s docstring: "a re-extraction genuinely changes what was
read and every review bound to the old text should come unbound."

Correct for a *changed* source. Wrong when nothing changed but the extractor
re-rolled. Model extraction is nondeterministic — temperature is rejected by
design, thinking is on by default — and stage-1 proposals are replace-loaded, so
every rebuild re-transcribes. One token of drift changes stage 2's snapshot id
and stales **every** downstream review as `input_changed`.

Mechanically correct per the binding rules; operationally a review treadmill
where human state can never converge.

`records.py:311` states proposals are "this run's output, not durable state," so
the records model has no home for a write-once artifact.

### The change

Extraction-class mappers land **pinned**: write-once, keyed by
`(source_digest, mapper_spec_id)`, where `source_digest` is the media content
hash. Re-extraction happens only on an explicit spec bump or an explicit
re-extract request — never as a side effect of a rebuild.

This does **not** violate no-cache. No-cache protects against stale *judgements*
being reused; the guarantee is that unreviewed judgement cells re-infer every
rebuild. A pinned transcription is not a judgement — it is a landed source
artifact, the same category as the `landed_text` an external ASR system would
have produced. The spec must state this distinction explicitly, because "we pin
extraction output" reads as a no-cache violation until the categories are
separated.

Requires a spec-level class marker (`mapper_class: extraction | judgement`) so
the harness knows which landing policy applies, and so the two are never mixed
in one spec.

### What it unlocks

Any staged extraction from any medium — the salvaged PDF path, S6's staged
image path, composition generally. Precondition for extension 1 being useful
beyond single-call media-direct scoring.

### Cost

A second landing policy in a records model built for one. Needs its own
fixture: extract, confirm a downstream review, replay stage 1 with drifted
output, assert the review **survives** (the inverse of the usual staleness
fixture).

---

## 4. `snapshot_scope: row | population`

### The problem

`input_snapshot_id` is derived **once** over the ordered projections of *all*
survivors (`mapper.py:383`) and stamped on every proposal (`:680`, `:870`); the
resolver compares against exactly that (`resolver.py:383`).

So appending one input stales **every** review in the population as
`input_changed`, even for rows whose own inputs are byte-identical. Score 400
tickets, confirm 30 reviews, add 50 tickets overnight → all 30 confirmations
lapse.

The design anticipated this for *reordering* — `canonical_sort` exists solely so
a reorder is a no-op — and not for *append*, the more common per-row no-op.
Incremental workloads are the norm, so this is the operational credibility of the
whole review story.

### The change

The spec declares which semantics it has:

- `snapshot_scope: row` — a row's snapshot hashes **that row's own**
  identity-bearing projection. Appends are review-stable. Correct for
  row-independent specs, which is most of them.
- `snapshot_scope: population` — today's behavior. Correct and **necessary** for
  cross-row specs, where a new input legitimately invalidates every verdict
  (S8 duplicate detection: adding a ticket can change every `dup_of`).

Not a bug fix — population scope is right for some specs and wrong for others,
and the spec is the only thing that knows which. Default should be `population`,
the conservative choice: over-invalidating loses reviewer time, under-invalidating
silently reapplies stale approvals.

`row` scope also makes partitioned runs coherent, which is the only honest path
to landing partial progress. `validate.py:711` blocks on any `skipped` cell
**unconditionally**, so under a too-small budget there is no way to land what
completed. Partitioning — each partition a complete population with its own
snapshot, gate, and landing — resolves S10 without a resume-from-ledger cache
(which *would* be the no-cache violation).

### What it unlocks

S9 (daily append), S10 (budget-bounded backfill, with partitioning), and makes
S7/S8's binding semantics a declared choice rather than an accident.

### Cost

Two snapshot semantics to keep coherent, and a migration question: existing
reviews were bound under population scope, so a spec switching to `row` must
either invalidate them once or map them forward. Fixture: two-run replay where
run 2 is run 1 plus one appended input; assert a run-1 confirmation survives
under `row` and lapses under `population`.

---

## Sequencing

1. **Extension 1** alone — media inputs. Unblocks image scoring immediately
   (single image → single row needs nothing else) and removes the PDF-shaped
   API. No dependencies.
2. **REVIEW.md H-2** — prerequisite for extension 2, and worth fixing regardless.
3. **Extension 4** — independent of the others, and the cheapest fix to the
   review story's credibility.
4. **Extension 2** — the big one. After H-2.
5. **Extension 3** — after 1 and 2, since pinning only matters once staged
   extraction can emit rows.

Extensions 1 and 4 are independent of the REVIEW.md fix list and could land in
parallel with it. Extensions 2 and 3 should not start until the five convergent
defects are fixed — building on a harness whose systemic failures land green is
how the defects become load-bearing.

## Deliberately not proposed

- **Chunked extraction with stitched evidence offsets** — cross-call state plus
  offset arithmetic across chunk boundaries is a different machine. Bound
  document size instead, or take a mechanical splitter.
- **Resume-from-ledger cache** — would make a partial run landable by reusing
  prior judgements. That is the no-cache violation the design correctly refuses.
  Partitioning achieves the operational goal without it.
- **Free-prose output fields** — substring evidence is category-inapplicable to
  synthesized text; see ARCHITECTURE's out-of-scope section.

---

# Implementation status

## Extension 1 — LANDED (docs + code + fixture)

`media.py` (new), plus changes to `transport.py`, `mapper.py`, `spec.py`,
`__main__.py`, and `samples/07-media-direct/`. Acceptance suite 7/7.

Decision taken: **permissive with a loud preflight.** A media-direct spec runs;
`spec.media_direct_report()` states at preflight that `verified` is unreachable,
for which fields, and how many. Derived from the declared fields rather than
trusting `max_unverified_share`.

What the implementation confirmed, beyond what was specced:

- **The validator needed no change at all.** `validate.py:387` returns
  `UNVERIFIED` whenever `landed_text is None`, so media-direct atoms cannot be
  marked `verified` regardless of what a model returns. This is a code path, not
  a fixture assertion — it is the strongest evidence in this document that
  "modality is a landing concern, not an evidence concern" (GENERALITY.md S5) is
  structurally true and not merely observed.
- **`_stamp_harness_version` was silently dropping spec fields.** It
  reconstructed `MapperSpec` field-by-field, so `accepts_media` vanished from
  every fixture's spec — and would have changed `mapper_spec_id` invisibly,
  invalidating every review with no visible cause. Now `dataclasses.replace`.
  Any future spec field would have hit the same trap.
- **The spec loader's strict key whitelist caught the omission** when
  `accepts_media` was missing from it. The guard works; worth keeping in mind
  that every new spec field needs two edits, not one.

### Known inconsistency, not fixed

`routing_table()` still reports `<field>.evidence_substring -> validate.py` for a
media-direct spec, where the substring check cannot run. The preflight warning
immediately below it says the opposite. Both lines are true in isolation —
the constraint *is* routed to the harness, and the harness *cannot* satisfy it
without a haystack — but printed together they read as a contradiction.

Fixing it means `routing_table` growing awareness of whether a haystack will
exist, which is input state rather than spec state. Left as-is deliberately: a
visible inconsistency in a preflight report is better than a routing table that
silently omits a constraint it does own.

### Not covered by the fixture

The fixture is `--dry-run`, like all seven. It replays a hand-authored response.
**No fixture in this suite has ever called the live API.** So fixture 07 proves
the harness treats media-direct evidence correctly; it proves nothing about
whether a model asked to describe an image region will comply rather than
fabricating a verbatim quote. That question needs a live call.

Also untested: `url` and `file_id` source forms (only `base64` has a fixture),
and multi-artifact inputs (one image per input only).

---

# Provider abstraction (added after extension 1)

## Why

Every fixture replayed a hand-authored response, so nothing had ever been checked
against a real model. Closing that gap through the paid API on each iteration is
expensive enough that it does not happen in practice.

`providers.py` adds a thin seam: a provider receives an already-built request and
returns a response object. It does **not** classify outcomes, count budget, retry,
or write the ledger — those stay in `transport.py`, so a development provider is
governed by exactly one failure policy.

## Verified: the Anthropic wire shape was already correct

Checked against the API reference before touching anything:

- `output_config: {"effort": ..., "format": {"type": "json_schema", "schema": ...}}` — matches
- `additionalProperties: false` at every object level — matches
- `thinking: {"type": "adaptive"}`, no `temperature`/`top_p`/`top_k` — matches
- the parse side iterates `content` for a text block rather than indexing
  `content[0]`, with the thinking-block hazard called out at `transport.py:1170` —
  correct, and the subtle one most implementations get wrong

So the provider work is additive; it did not fix a wire defect.

## `claude_cli` — a development aid, NOT an equivalent

Eight divergences, recorded on every attempt rather than documented and forgotten:
no `output_config` (schema requested in prose, conformance unenforced); fenced
output; **media arrives as a filesystem `Read`, not a content block**; agent loop
rather than one call; no effort control; the CLI's own ~13k-token cached harness
prompt in context; system prompt concatenated into the user turn; token counts not
comparable.

The media one matters most: this provider therefore **cannot** validate the media
content-block path — only whether a model can read the artifact at all.

`AttemptRecord` gained `provider` and `provider_notes` so this travels with the
audit trail. A `claude_cli` attempt is no longer indistinguishable from a real API
call, which was the state before and defeated the point of tracking divergence.

Replayed attempts record `provider: "replay"` — not `"anthropic"`. A recorded
fixture is a *claim* about what some provider once said; the ledger must not
restate that claim as a call it observed.

## What running it against a real model found

**A bug in my own fence extraction.** The first live run blocked with
`schema_reject` on four consecutive attempts. The transport calls all succeeded —
the model answered, and its JSON was structurally perfect. The defect was mine: the
model appended an explanatory paragraph *after* the closing fence, and my regex was
end-anchored, so the whole blob went to the JSON parser. Fixed by searching for the
block instead of requiring the response to be nothing but the block.

This is exactly the class of defect no hand-authored fixture would have caught,
because a fixture author writes the response they expect.

**Real nondeterminism, on the same image.** Two consecutive runs on the identical
PNG produced different outcomes: once `ok`/`ok` with values `ABC-1023`/`90.0`
matching the hand-authored fixture, once `evidence_absent`/`evidence_absent`. The
model declined to answer on the second run.

Consequences worth stating plainly:

- The design's accepted non-determinism (decision 1) is now **observed**, not
  assumed. It is a real property of this harness, at a magnitude that flips
  `value_status` between runs rather than merely perturbing a value.
- A fixture asserting exact `status_counts` is therefore **not** stable under a
  live provider. `verify` remains dry-run-only for good reason, and this is that
  reason rather than a convenience.
- Under a value-bound review, every such flip is a `value_changed` staleness event
  — GENERALITY.md S11's review-treadmill mechanism, now demonstrated on a
  *grounded* field rather than only predicted for ungrounded enrichment.

**CV-5 fixed in passing.** `_live_caller` built `TransportConfig(effort=...)`,
dropping `spec.model`, so a live run called the default model while
`mapper_spec_id` claimed another. Now `TransportConfig.from_spec`.

## Still not covered

The **Anthropic** provider has still never run — no API key, and `anthropic` is
absent from the pinned venv. So the real content-block path, real schema
enforcement, and real `stop_reason` handling remain unexercised. `url` and
`file_id` media forms have no fixture either.

---

# The real API's PDF constraints (checked 2026-07-30)

The `claude_cli` run proved a model can read a generated PNG. It proved **nothing**
about the API path, because the CLI reaches media through a filesystem `Read` tool.
These are the actual constraints, from the API reference rather than inference.

## Hard limits — and which are provider-specific

These are **first-party Claude API** figures. Two of them move depending on where
the call goes, which matters because a spec pins a model, not a platform.

| Constraint | 1P Claude API | Varies? |
|---|---|---|
| Request size | **32 MB** | **YES** — Bedrock **20 MB**, Google Cloud **30 MB**, Claude Platform on AWS same as 1P |
| Pages per request | **600** (100 under a 1M-token context window) | Conditional on context window, so it moves with the model |
| Format | Standard PDF, no passwords or encryption | No |
| Token cost | **1,500–3,000 tokens/page** text, *plus* image tokens — every page is rasterised | No (it is how the model reads a PDF) |

Both size and page limits apply to the whole request, not per document. The docs
warn that dense PDFs "can fill the context window before reaching the page limit,"
and that large PDFs "can also fail before reaching the page limit, even when using
the Files API."

**Feature availability by platform** (1P / Claude Platform on AWS / Bedrock /
Vertex / Foundry):

| Feature | Availability |
|---|---|
| PDF input | GA everywhere except Foundry (beta) |
| Citations | GA everywhere except Foundry (beta) |
| Structured outputs | GA everywhere except Foundry (beta) |
| **Files API** (`file_id` media) | **beta on 1P / P-AWS, NOT SUPPORTED on Bedrock or Vertex** |

That last row is a real constraint on extension 1's design. `MediaInput` offers
`file_id` as the cost-efficient source form — upload once instead of re-sending
base64 on every validation retry — and it **does not exist on Bedrock or Vertex**.
So the cheap path for large documents is first-party-only, and a spec relying on it
is not portable. Worth stating in `media.py` rather than discovered at runtime.

The 20 MB Bedrock ceiling is the tightest of the three, so a base64 PDF sized
against the 32 MB figure can fail on a platform the spec never named.

Consequence for `estimate()`: `_PDF_TOKENS_PER_KB = 4.0` is a size-based heuristic,
but the real driver is **pages**, and each page costs text *and* image tokens. For a
40-page PDF the estimate is likely wrong by a large factor in an unknown direction —
which violates the estimator's own stated principle that it must err high.

## The API extracts PDF text server-side

This is the finding that matters most, and it invalidates part of the two-stage
design's premise.

The design assumed a native PDF block has "no mechanical substring surface — the API
sees rendered content, the validator holds base64 bytes." That is **wrong for text
PDFs**. The API extracts text server-side and chunks it into sentences.

More: with `"citations": {"enabled": true}` on the document block, the response
carries citation objects whose `cited_text` is **extracted by the API from the
document**, not generated by the model. The reference states citations are
"guaranteed to contain valid pointers to the provided documents."

For a PDF the location shape is:

```python
{
    "type": "page_location",
    "cited_text": "The exact text being cited",   # free — not counted as output tokens
    "document_index": 0,
    "start_page_number": 1,   # 1-indexed
    "end_page_number": 2,     # exclusive
}
```

So the API offers, natively, most of what the two-stage design was built to
reconstruct: verbatim source text with page locations, structurally incapable of
fabrication because the model never authors the quote.

## The blocking incompatibility

**Citations and structured outputs cannot be used together.** Enabling citations on
a document block *and* sending `output_config.format` returns a **400**. The reason
given: citations interleave citation blocks with text output, which the strict JSON
schema path cannot express.

This is a genuine fork, not a tuning knob. The harness currently depends on
`output_config.format` for every call.

| Path | Get | Lose |
|---|---|---|
| **Structured output** (today) | Schema-enforced JSON; a response either conforms or is a `SCHEMA_REJECT` | Model-authored quotes — fabrication is possible, and the substring check is the only defence |
| **Citations** | `cited_text` extracted by the API; fabrication structurally impossible; page locations free | No schema enforcement; the harness must parse prose and validate shape after the fact — exactly the `claude_cli` weakness, on the paid path |

Worth stating plainly: the citations path would make the harness's central
anti-fabrication mechanism *unnecessary* for text PDFs, and simultaneously remove
the schema guarantee the rest of the harness leans on. Which fork wins is a real
design decision, currently unmade.

## What does NOT work

- **Scanned / image-only PDFs are not citable.** "PDFs that are scans of documents
  and do not contain extractable text are not citable." So the citations path covers
  text PDFs only, and a scanned page falls back to `evidence_unverified` — which is
  what GENERALITY.md predicted for any medium without a text layer.
- **Image citations do not exist.** So fixture 07's screenshot case is
  `evidence_unverified` on the API path too, exactly as built. That part of
  extension 1 needs no revision.

## Revised view of the PDF blocker

Earlier framing: nothing in the venv extracts PDF text, so stage 1 needs a
dependency or a circular model call. **That framing was incomplete.** For a text
PDF the API extracts the text itself and will hand back verbatim cited spans with
page numbers, for free, if the harness gives up structured output.

The residual blockers are narrower than stated:

1. **Paging**, not text extraction — 600 pages/request, and dense documents fail
   earlier. Splitting still needs a page-count, which still needs a PDF library.
2. **The citations/structured-output fork** — an unmade decision, not a missing
   capability.
3. **Scanned PDFs** — genuinely need OCR, and are honestly `evidence_unverified`
   until then.
4. **Multi-row output** — unchanged; extension 2 regardless of which fork wins.

## Estimator work this implies

`estimate()` should take page counts, not just byte sizes, and price text + image
tokens per page. Today a media-heavy preflight is confidently wrong. The 32 MB
request ceiling should also be a preflight refusal rather than a 413 discovered
mid-population.
