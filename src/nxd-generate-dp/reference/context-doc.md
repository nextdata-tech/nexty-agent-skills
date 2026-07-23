# CONTEXT.md — the in-closure design/process record

## Contents

- Why this file exists
- When to write it
- What it MUST contain
- Boundary rule (enforced by the self-check)
- Template

## Why this file exists

The closure carries a **queryable data product** but, without this file, not the
**design and process context** that makes the work continuable. A fresh session
handed only the closure can reconstruct *what a base model is* and *how to reopen
it*, but cannot continue to a promised-but-unbuilt derived model, cannot
reproduce the row set, and cannot tell inference from stated fact — because the
rulings behind those live in the author's head or in an external doc.

The failure this prevents: a promised derived model (a scoring/classification
model) whose contract — the rubric, thresholds, verdict set — sits in a narrative
doc **outside** the closure that the closure only *references* (`../../design.md`).
That pointer is dangling across the package boundary: the moment the closure is
handed off or moved, the contract is gone and the derived model cannot be built.

**Rule: everything a later session needs to continue the work lives INSIDE the
closure.** `CONTEXT.md` is that record. It is prose for a human/agent to read;
machine-enforced rulings still land as data (`nxd_decisions`) and executable
asserts (Step 3b) — `CONTEXT.md` does not replace those, it explains them.

## When to write it

**Always** — every closure emits `CONTEXT.md` at the root. It is a required
closure file, checked by the self-check (Phase C).

## What it MUST contain

A closure `CONTEXT.md` at the closure root, with these sections:

1. **Intent** — one paragraph: what the DP is for and the questions it answers.
2. **Population & sample-selection rule** — the exact, reproducible rule that
   defines which rows are in the source. If the source was **sampled** (you did
   not take the full population), state the selection rule verbatim and why it is
   reproducible — a rerun over the same source must select the same rows. A
   sample rule that is deterministic but arbitrary (e.g. "the oldest N") is a
   liability: name what it excludes and whether the excluded rows matter to any
   downstream model. If a downstream step depends on a field, sampling must not
   drop rows where that field is absent — call that out here.
3. **Per-field inference & determinism caveats** — every field that is
   **inferred** rather than a verbatim source value (Step 1a rulings, sanctioned
   inferences like deriving location from other columns). For each: what it is
   derived from, and that it is the field most likely to **drift on a rerun**.
   This mirrors the dimension `description=` in `models.py` but states the
   *ruling*, not just the flag. Where a ruling was **supplied by the user**, say
   so and name it — a landed rubric row the user wrote and one you authored are
   indistinguishable in the table, and only this line tells them apart.
4. **Required-capture fields** — any source field a downstream model, gate, or
   verdict **depends on**, identified by reading backward from every promised
   derived model and any gating/verdict logic to the source fields it consumes.
   State that its capture is required, and record any row where it is missing. A
   field that is *referenced in the source but not extracted* is an incomplete
   extraction, not a valid absent value — surface it for recovery, never pass it
   as absent. A missing required field silently disables the downstream step (it
   runs and produces nothing; no assert fires). This is a general stage-to-stage
   dependency rule, independent of what the field is.
5. **The derived-model contract, in full, for every model still to be built** —
   its complete contract lives in the closure. Two shapes, preferred first:
   (a) **best — author the inert derived model itself** (its `semantic_model`, an
   empty-bodied `@dlt.resource`, listed in `PHYSICAL_MODELS`, the contract as
   schema + Step-3b asserts) so it is executable *and* satisfies the naming
   invariant; (b) **if the logic is genuinely deferred to a later session, the
   model is not yet `.promise`d** — the naming invariant requires every promised
   model to be in `PHYSICAL_MODELS`, so a promised-but-unbuilt model fails Phase A
   — and its contract is carried as a structured `contracts/<name>.md` with
   mechanically-readable sections: `## inputs`, `## rule` (input→output mapping /
   gates / thresholds), `## output schema` (columns the model must promise),
   `## verdict set` (allowed output values, if any). Name it in the "Models still
   to build" section below, and `.promise` it only once authored. **Never** a
   pointer to a file outside the closure, and never a rubric left only as free
   prose here in `CONTEXT.md` when a derived model depends on it.
6. **Reopen recipe** — the workflow id and this closure's absolute path (together
   the only durable key; bearer tokens do not persist) and the
   `build_data_product` → `describe_models` → `run_semantic_query` sequence.
   The supervisor exposes **no** list, status, resume, or rediscovery tool, so
   reopening is always a rebuild. Write the recipe so it stands alone: a cold
   reader may not have this skill loaded.
7. **Credentials** — only when `infra-profile.yaml` carries live credentials
   (a `*-source` service with a populated `attributes:` list). Name the file and
   the **keys**, never a value, and give the rotation step. `SENSITIVE` warns a
   reader who opens the directory; this section reaches the one who reads
   `CONTEXT.md` first. Omit the section entirely for a file/CSV closure — an
   empty "no credentials here" line invites a later editor to fill it in.
8. **Known blockers** — any runtime issue seen while building (e.g. a build/serve
   readiness timeout), kept **separate** from artifact correctness so a later
   session does not mistake a transient runtime failure for a broken closure.

## Boundary rule (enforced by the self-check)

- `CONTEXT.md` MUST exist at the closure root.
- No closure file (`CONTEXT.md`, `README.md`, `spec.py`, `models.py`,
  `transform/main.py`, `contracts/*`) may reference a **contract or design doc by
  a path that escapes the closure** (a `../`-rooted path). A promised derived
  model's contract must resolve inside the closure. A pointer that leaves the
  closure is a dangling reference and fails Phase C.

## Template

```markdown
# CONTEXT — <dp-name>

Workflow id:   <workflow-id>
Closure path:  <abs path to this dir>
(Together these are the durable key across sessions. Bearer tokens never persist.)

## Intent
<what this DP is for; the questions it answers>

## Population & sample-selection rule
- Source population: <the full set, and how it is identified>
- Sample rule (if sampled): <exact reproducible rule>. Reproducible because <why>.
- Excludes: <what this rule leaves out, and whether any downstream model cares>.

## Inferred fields & determinism caveats
- <field>: inferred from <basis>. NOT a stated source value — most likely to
  drift on a rerun. (Mirrors the models.py dimension description.)
- <field>: verbatim source; no inference.

## Required-capture fields (downstream depends on these)
- <field>: required by <downstream model/step>. Missing for rows: <ids or "none">.
  If missing, <downstream step> runs and produces nothing (silent no-op).

## Models still to build (not yet promised)
- <derived-model-name>: logic added <when>. Contract in
  `contracts/<derived-model-name>.md`; `.promise` it once authored.
  (Or author it inert now and promise it — preferred.)

## Reopen
The supervisor exposes only build_data_product, describe_models and
run_semantic_query — there is no list, status, resume or rediscovery tool, and
the bearer token is never persisted. Reopening is therefore always a rebuild,
which costs a full build; it is not a reattach to a running instance.
1. build_data_product(definition="<abs path to this dir>", workflow="<workflow-id>")
2. describe_models — using the endpoint and bearer that call returned
3. run_semantic_query — same endpoint and bearer

## Credentials (omit this section entirely if there are none)
This closure holds a live credential in plaintext.
- File: infra-profile.yaml — service <service-name>, keys: <key names only>
- Rotate: replace the `value:` entries and rebuild the data product.
- Do not commit, zip, or attach this directory. `.gitignore` covers
  infra-profile.yaml; the other files are safe to share only if the data is.

## Known blockers (separate from artifact correctness)
- <e.g. build/serve readiness timeout>: <symptom>, <remedy>. The closure
  self-check (A/B/C/D) passing is independent of this runtime issue.
```

## `contracts/<name>.md` template (one per model still to build)

Prefer authoring the inert derived model instead — it satisfies the naming
invariant and is executable. Use this file only when the logic is genuinely
deferred to a later session, in which case the model is **not yet `.promise`d**
and this contract (plus the `CONTEXT.md` entry naming it) is what makes it
buildable by a cold reader.

```markdown
# contract — <derived-model-name>

## inputs
<which base/derived models and columns this model reads>

## rule
<the input→output mapping: the derivation, gates, thresholds, calibration —
everything a later session needs to author the transform, with nothing left to
re-derive>

## output schema
<the columns this model must promise, with types — what models.py declares>

## verdict set
<the allowed values for any classification/verdict column; omit if none>
```
