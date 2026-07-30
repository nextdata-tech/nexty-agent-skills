# The policy read-back gate, in full

The one failure this skill treats as unrecoverable is a closure whose scoring
policy the user never saw. This file is the complete gate; `SKILL.md` carries
the short form.

## Contents

- [When it fires](#when-it-fires)
- [What is forbidden until the user replies](#what-is-forbidden-until-the-user-replies)
- [The read-back artifact](#the-read-back-artifact)
- ["Use your judgement" is not approval](#use-your-judgement-is-not-approval)
- [Invoked directly](#invoked-directly)
- [Invoked as a generation subagent](#invoked-as-a-generation-subagent)

## When it fires

The request supplies a procedure — a rubric, gates, weights, thresholds, scales,
a verdict vocabulary, a selection rule — **with a gap that changes a score, a
verdict, a gate outcome, or which rows land**:

- a scale defining only some levels (5 and 1 given, 2/3/4 absent);
- named verdicts with no score→verdict mapping, or no precedence between them;
- a qualitative modifier that must become a rule ("unless exceptional");
- a gate whose UNKNOWN / missing / inferred value could change the outcome;
- evidence with no provenance rule, or no missing-evidence rule.

`scripts/validate_dp_spec.py` detects every one of these mechanically over the
IR, which is why the read-back is a structured file rather than a paragraph.

**A fully specified procedure** still gets read back and confirmed, but expect
one short turn. **No procedure in the request** means this gate does not fire —
do not manufacture one.

## What is forbidden until the user replies

Do NOT: create the closure directory · copy source data into it · write any
closure file · generate transform code · create tables · score rows · invoke a
build.

Allowed: reading the source and its headers; writing `dp-spec.md` itself (it
lives **outside** the closure, so it is not a materialization); asking technical
delivery questions.

**A delivery answer is not policy approval.** Deterministic-vs-manual, extra
outputs, naming — answering these does not satisfy this gate. Never proceed on
your own recommended defaults.

## The read-back artifact

`dp-spec.md` — the user-editable IR, written beside the closure and validated
with `scripts/validate_dp_spec.py`. Schema and authoring modes:
**nxd-pocket-loop**'s `reference/dp-spec.md`.

It must **enumerate**, in the user's vocabulary and understandable without
reading generated code:

- objective and scope;
- source and re-run approach;
- gates, with explicit UNKNOWN handling;
- each criterion weight;
- **every anchor you propose for an incomplete scale**;
- score aggregation;
- **proposed verdict bands and their precedence**;
- provenance and missing-evidence behaviour.

Never summarize a procedure the user must check. Then show the file, say that it
all lands as editable rows rather than hidden judgement, **name every value you
authored**, ask for a correction or approval, and wait.

A validator pass is **not** approval — it only means the spec is compilable.
`status: approved` is the user's to set, never yours.

Approved policy lands as rows: [derivation-plan.md](derivation-plan.md).

## "Use your judgement" is not approval

*"I don't have those defined, use your judgement but write it down"* licenses you
to **author the proposal** — then show it and wait again. It never licenses
skipping the turn. A value you authored stays `provenance = agent_authored` in
`nxd_decisions` however the user later approves it: approval moves `status`, and
never authorship.

## Invoked directly

Without **nxd-pocket-loop** having gathered intent, source, questions and the
procedure, that gathering has not happened, so this gate has not been satisfied.
"The user asked for a data product" is not a settled plan: run the read-back
here, or hand back to `nxd-pocket-loop`.

## Invoked as a generation subagent

The orchestrator ran the read-back, the user approved, and the approved
`dp-spec.md` (or the policy enumerated verbatim) arrived in your prompt. The
**user turn is the orchestrator's; you never open one.**

The gate is not a rubber stamp. Re-run the [when it fires](#when-it-fires)
criteria against the approved policy and **bounce** — write nothing, return
`gap_found: <what and why>` — when:

- a policy element is absent from the approved text, or
- a profiling finding makes an approved element ambiguous or conditional in a
  way the approved text does not resolve.

Encoding a defensible-but-unseen interpretation is the same unrecoverable
failure as skipping the gate.

On the happy path: carry the approved text verbatim into `CONTEXT.md` and
`nxd_decisions`, and **surface the encoded bands in your return** so the
orchestrator can confirm shipped-matches-approved.

**You hold no credential for a db/API source and must not be given one:** write
a placeholder in the `attributes`, return `credential_slots` (key names only,
never a value), and report the connectivity dry-run as **not run** — the
orchestrator injects the real value host-side.

Dispatch/return contract: **nxd-pocket-loop**'s `reference/scheduling.md`.
