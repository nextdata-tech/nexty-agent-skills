---
id: 2026-08-24-blueprint-procedure-encapsulation
date: 2026-08-24
label: "a resolved procedure value is a landed model, and a clock-relative Term names its anchor"
plugin_version: 0.38.6
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — a resolved procedure value is a landed model, not a literal

## Notes

No eval arm distinguishes this. The scenarios that author a blueprint supply
fully specified procedures, so the gap these rules close never opens in them; an
arm would compare two runs that make the same plan. The shape that separates
them is an underspecified rubric reaching construction, which is a
conversational state rather than a fixture. The carrying tests are the evidence.

**What was wrong.** The policy gate already named the gap class generically — *"a
scale defining only some levels (5 and 1 given, 2/3/4 absent)"* — so the pack
knew to **ask**. Nothing stated **where the answer goes** once given.
`reference/dp-blueprint.md` had no occurrence of `rubric`, `band` or
`threshold`, so a resolved threshold could legally become a literal in
`transform/main.py`: the prose travelled to the next reader and the executable
logic did not.

The construction-side rule existed (`derived-models.md`: band ids come from the
landed rubric, never a transform literal) but is reached only by whoever writes
the closure, and cannot help when the blueprint declared no model to hold the
bands.

**Observed.** A blueprint declared a five-criterion rubric whose one
`deterministic` criterion had a 1–5 scale with anchors for 5 and 1 only, and a
`scoring_rubric` model whose columns were exactly those two anchors plus a
range. No column could hold a band, so the day boundaries deciding the score
became literals, and a reader of the blueprint could not tell what the middle of
the scale did. A second ruling in the same closure went the same way: a Term
defined against *"the fetch time"*, which a derived model cannot read, resolved
to `max(updated_at)` in a code comment.

**Why the gate alone was not enough.** It fires once, in one session, and not at
all on a blueprint already approved with the gap inside it — which is how that
closure reached construction with nothing left to fire. A representation rule is
structural: the bands come from a landed model or the ladder does not exist.

**Placement.** Both new subsections are section-terminal. A `###` placed
mid-section makes the general `##` commentary that follows it — what `Sections`
deliberately omits, what the extraction layer derives from `Terms` — render as
the subsection's own content. The doc's existing `### Sharing the document`
already follows that pattern.

**Scope.** This closes the two *content* gaps that kept a blueprint from being
self-contained as a plan. It deliberately does nothing for the consent items —
mapper thresholds, the grant, the credential — or for the typed-proposal binding
that stops approval travelling with the document alone.

## Evidence

- `evals/tests/test_blueprint_procedure_contract.py` — 5 tests pinning the
  landed-model rule, the underspecification test a reader can apply, the
  clock-anchor rule, the generator gate's pointer at the first, and the
  section-terminal placement of both blocks. Verified to fail against the
  previous implementation: **all 4 original tests fail** with
  `reference/dp-blueprint.md` and `nxd-generate-data-product/SKILL.md` reverted;
  the placement test fails against the first revision of this branch.
- `src/nxd-generate-data-product/SKILL.md` stays at exactly 500 lines, the
  validator's documented cap — the gate pointer was packed onto an existing line
  rather than wrapped, because that file was already at the limit.
- `python3 scripts/validate_skills.py --root .` — passes.
- `./build-skills.sh` — packages, 200-entry cap respected on every skill.
- `python3 evals/benchmark_record.py --check` — entries and index valid.
