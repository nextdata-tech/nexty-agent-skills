# Scenario: Annotation Completeness for Queryability

This scenario tests one thing the other semantic scenarios cannot: whether the
agent annotates what the **questions did not name**.

`generate-runnable-dp-from-intent` hands the agent an `inferred_model.json`
that already carries every role and every description, so it can only measure
whether the handoff survived transcription. Here there is no handoff. The agent
gets two CSV exports and two narrow questions, and must decide for itself what
the remaining columns are — including several the questions never mention.

The export is deliberately built with four traps:

- **`payments.method`** — an obviously sliceable low-cardinality column that no
  question asks about. Annotating only what the questions need leaves it bare,
  and a bare column produces no metric, dimension or join and never appears in
  `describe_model`.
- **`payments.status` vs `payments.state`** — near-identical names carrying
  unrelated meanings (payment lifecycle vs. the payer's regional code). Names
  alone cannot separate them; only the descriptions can.
- **`payments.payer_email`** — personal data no question asks for. The PII flag
  has to come from the profiled values, not from the questions.
- **`payments.balance_after`** — a running account balance. It is numeric and
  additive-looking and summing it answers nothing, so it must not become a
  `sum` metric — but it must not be left bare either.

## Task for the agent

Two CSV exports are in your workspace under `data/` — `data/payments/payments.csv`
and `data/merchants/merchants.csv`. Two stakeholders have asked the questions
listed below.

1. Profile both exports before authoring anything, and save the combined
   profile as **`schema.json`** in your workspace: actual columns, declared
   types, null rates, cardinalities and sample values for both tables in one
   document. Ground every decision in it — never invent or rename a column.
2. From `schema.json` **and** the questions, infer and author the semantic
   models in a single **`models.py`**, using the public `nxd.spec` DSL. Declare
   each table's grain, the relationship between them (validated against the
   data, not name similarity), the metrics the questions need with correct
   aggregations, and the dimensions.
3. In your final answer include: (a) the complete final `models.py` verbatim,
   (b) for each of the two questions, which declared concepts answer it, and
   (c) for **every** column you did NOT give a role, one line saying why it
   does not need one.

   For (a), wrap your one authoritative final `models.py` between two marker
   lines, each on its own line, with NOTHING else on those lines:

   ```
   ===BEGIN FINAL models.py===
   <the complete final models.py source>
   ===END FINAL models.py===
   ```

   Emit **exactly one** such marker pair. A code fence immediately inside the
   markers is optional and ignored.

## Stakeholder questions

1. "What's our total payment volume by merchant category?"
2. "How many payments did we take each month?"

## Required artifacts from eval runner

- `fixtures/data/payments/payments.csv` and `fixtures/data/merchants/merchants.csv`
  — the two exports (provided; copied into the agent workspace as `data/`).
- The `duckdb` Python package must be obtainable in the workspace (e.g. via
  `uv run --with duckdb`) for the profiling step.
- No acceptance script ships with this scenario: the deliverable is the
  inferred and annotated `models.py`, graded from the verbatim copy in the
  final answer.
