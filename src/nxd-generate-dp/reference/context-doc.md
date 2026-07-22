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
   *ruling*, not just the flag.
4. **Required-capture fields** — any source field a downstream model or step
   **depends on** (a URL a later evaluation needs, a key a later join needs).
   State that its capture is required, and record any row where it is missing —
   a missing required field silently disables the downstream step (a no-op that
   does not error).
5. **The derived-model contract, in full, for every promised model not yet
   built** — if `spec.py` promises a derived model whose logic is authored in a
   later session, its complete contract lives HERE (or in `contracts/<name>.md`
   in the closure): the rule that maps inputs to outputs, thresholds/gates, the
   output schema, the verdict/label set. **Never** a pointer to a file outside
   the closure. Better still, author the derived model's `semantic_model` +
   `@dlt.resource` inert (Step 3a) so the contract is code, not prose — but if it
   is deferred, the prose contract is mandatory and in-closure.
6. **Reopen recipe** — the workflow id (the only durable key; bearer tokens do
   not persist) and the `list_data_products` → `resume_data_product` /
   `build_data_product` → `describe_models` → `run_semantic_query` sequence.
7. **Known blockers** — any runtime issue seen while building (e.g. a build/serve
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

Workflow id: <workflow-id>   (the only durable key across sessions)

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
  If missing, <downstream step> becomes a silent no-op.

## Deferred derived-model contracts (full, in-closure)
### <derived-model-name>  (promised in spec.py, logic added <when>)
- Inputs → output rule: <the mapping / rubric>
- Gates / thresholds: <...>
- Output schema: <columns the derived model must promise>
- Verdict / label set: <the allowed values>
  (Prefer authoring this as inert code in models.py + transform/main.py; if
  deferred, this prose contract is the durable copy and MUST stay in the closure.)

## Reopen
1. list_data_products — is <workflow-id> published?
2. yes → resume_data_product(workflow="<workflow-id>")
3. no  → build_data_product(definition="<abs path to this dir>", workflow="<workflow-id>")
4. describe_models → run_semantic_query

## Known blockers (separate from artifact correctness)
- <e.g. build/serve readiness timeout>: <symptom>, <remedy>. The closure
  self-check (A/B/C) passing is independent of this runtime issue.
```
