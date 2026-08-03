# Field mapper — mapping from inside a transform

The one sanctioned way a transform may call a model. Everything else about
inference in a closure is agent-side and lands as CSV before the build; this is
the exception, and it is gated by consent rather than trusted.

## Contents

- [When to use it (and when not to)](#when-to-use-it-and-when-not-to)
- [Vendoring it into a closure](#vendoring-it-into-a-closure)
- [Authoring the spec and the grant](#authoring-the-spec-and-the-grant)
- [Evidence modes — what each one proves](#evidence-modes--what-each-one-proves)
- [Reviews: `data/mapper_reviews/`](#reviews-datamapper_reviews)
- [Two dlt runs, in this order](#two-dlt-runs-in-this-order)
- [Spend: the self-check really pays](#spend-the-self-check-really-pays)
- [What the consent gate cannot see](#what-the-consent-gate-cannot-see)
- [Verifying a vendored copy](#verifying-a-vendored-copy)

## When to use it (and when not to)

Use [reference/llm-judgments.md](llm-judgments.md) — agent-side judging, landed
as CSV — whenever the judgements are a **fixed set** you can enumerate once: FX
rates, merchant→category rulings, a rubric applied to a bounded list. That path
needs no vendored package, no grant, and no model call at build time.

Use the field mapper only when the mapping must run **over rows the transform
itself produces**, so no fixed CSV can be authored ahead of it. It brings real
cost: a vendored package in the closure, a consent grant the user must author,
and live model calls during the self-check.

## Vendoring it into a closure

The harness is **not a wheel**. Copy it out of this installed skill:

```bash
cp -R "<skill-dir>/mapper/field_mapper" "<closure>/field_mapper"
```

`<skill-dir>` is the directory containing the running `SKILL.md` — installed,
that is `~/.claude/skills/nxd-generate-data-product/`. The destination name must be
literally `field_mapper` at the **closure root**; that is the import name the
package uses internally and the name the consent gate triggers on.

Drift between closures is re-consented rather than silent: `harness_version` is
an input to `mapper_spec_id`, so vendoring a newer harness moves every spec id,
existing grants stop binding, and the gate demands fresh ones.

## Authoring the spec and the grant

Write the mapper spec as JSON under `contracts/` (for example
`contracts/mapper_spec.json`) and load it with `MapperSpec.load`. A spec inlined
as a Python literal has no stable id, so nothing can be consented to.

Compute the id the grant must carry:

```bash
python -m field_mapper spec-id contracts/mapper_spec.json
```

Paste that value into the grant's `mapper_spec_id` and write the grant to
`contracts/`. A hand-computed hash, or the `"<derived>"` placeholder the
`samples/` fixtures use, binds nothing — the gate rejects `<derived>` by name.

`python -m field_mapper grant-check <spec> <grant>` applies the same statically
decidable checks the gate subprocesses (hash, primary and corroboration model,
expiry) and prints JSON. It does **not** reject `<derived>`; the gate does that
before ever calling it, so on that one input the two answers differ.

**Consent is the user's act.** You cannot author a grant on the user's behalf,
extend an expiry, or decide a drifted rubric is still acceptable. Editing the
spec — the instruction, a threshold, the target fields, the model — moves the id
and revokes the grant on purpose.

Thresholds have **no defaults**: `max_degrade_share`, `max_error_rate` and
`max_unverified_share` must be declared, and a wrong default would be worse than
an absent one. `max_absent_share` is genuinely optional.

## Evidence modes — what each one proves

| Mode / path | Evidence kind | What it actually proves |
|---|---|---|
| `structured` over text already landed in the closure | `verified` | The quoted span is a substring of landed text; re-checkable offline from `text_hash` + offsets. |
| `evidence_mode: "citations"` | `api_cited` | The API extracted `cited_text` server-side from the document, with page locations — a second party, not the answering model. Verified-equivalent for gating, but not offline-re-runnable. |
| Media sent direct, no citations | `evidence_unverified` | Nothing. It counts against `max_unverified_share` by design. |

Scanned PDFs are not citable, and image citations do not exist. Page counting is
stdlib-only and returns `None` for encrypted or compressed PDFs, which degrades
the **cost estimate**, not the mapping.

## Reviews: `data/mapper_reviews/`

Human reviews live **inside the closure**, at
`data/mapper_reviews/batch-NNN.csv`. They survive `write_disposition="replace"`
because dlt replace-loads the full glob every run, and `mapper_reviews` is an
ordinary base model.

- **To review**: add `data/mapper_reviews/batch-<next>.csv`.
- **To revoke or correct**: add a **new row**, never edit an existing one. Rows
  are immutable and append-only, like the ledger.

The tradeoff is stated rather than hidden: durable human state sits inside
`data/` beside agent-managed exports, protected by the "preserve a file
connector's supplied export exactly" convention. A wiped `data/mapper_reviews/`
is *loss* — the reviews are gone and the cells re-infer — never *corruption*,
because `bound_value_hash`, `bound_input_snapshot_id` and `bound_mapper_spec_id`
make it impossible for a review to silently attach to the wrong value.

## Two dlt runs, in this order

A mapping transform is **two** `pipeline.run` calls, not one:

1. **run 1** lands the base rows.
2. **read** them back out of the loaded destination.
3. **map** those rows with `map_inputs`.
4. **gate** on the result — block the build if the spec's thresholds are
   exceeded, *before* landing anything derived.
5. **run 2** lands the proposals, evidence and ledger.

The order is load-bearing. Mapping before run 1 maps rows that may never land;
landing derived rows before the gate publishes judgements the thresholds would
have rejected.

`mapper/examples/e2e/` in this skill's repo checkout holds both proofs —
`run_e2e.py` for the data chain and `transform_main.py` for the platform
entrypoint. They are not packaged into the installed skill: they need an nxd
monorepo checkout.

## Spend: the self-check really pays

Phase B of the self-check **executes** the transform, and the harness resolves
its API key from secrets with an environment fallback. With `ANTHROPIC_API_KEY`
set, self-checking a mapper closure makes **live model calls**. Phase G runs
before Phase B precisely so that spend can only happen under a binding grant;
the ceilings on the spend itself (`max_calls`, `max_tokens`, `max_usd`) are
enforced inside the harness at call time, not by the gate.

## What the consent gate cannot see

Green Phase G means a binding consent artifact exists. It is not proof that no
unconsented mapping happened, and the full list of what it misses — the
self-attested hash, the decoy-spec limit, renamed vendor directories, runtime
coverage versus static binding — is in
[reference/self-check.md](self-check.md) § "What Phase G cannot see". Read it
before treating a green gate as a safety guarantee.

## Verifying a vendored copy

The fixtures ship with the skill and are the acceptance suite, not a demo:

```bash
python -m field_mapper verify "<skill-dir>/mapper/samples"   # expect 13/13
python -m field_mapper pins                                  # spec-id stability
```

Record schemas, `value_status` semantics, the blocking rules and the resolution
order are normative in `mapper/CONTRACT.md`.
