# Planning the derivation — from questions to required models

## Contents

- [Why this step exists](#why-this-step-exists)
- [Backward-chain from the questions](#backward-chain-from-the-questions)
- [A worked chain](#a-worked-chain)
- [Base or derived? the decision test](#base-or-derived-the-decision-test)
- [Reference data: rulings that exist in no source CSV](#reference-data-rulings-that-exist-in-no-source-csv)
- [Rulings you must NOT propose](#rulings-you-must-not-propose)
- [Confirm the plan before authoring](#confirm-the-plan-before-authoring)

## Why this step exists

The semantic layer is deliberately narrow. A dimension is a pointer at a
physical column — there is no expression surface, so no `CASE WHEN`, no
`DATE_TRUNC`, no concatenation. A metric is strictly one aggregate over one
column — there are no filtered metrics, no ratio metrics and no default
filters. Nothing in the layer generates a row or removes one.

Every one of these is therefore **not** a query-time concern:

| Ruling | Why the semantic layer can't express it |
|---|---|
| "AWS spend is COGS, not opex" | needs a classification column that does not exist |
| "transfers are never expenses" | needs a filtered metric, or a row that isn't there |
| "amortize prepayments over the term" | needs one input row to become N output rows |
| "dedupe refund pairs" | needs rows removed — a self-anti-join |
| "normalize everything to USD" | needs an expression over an FX rate |
| "report monthly" | needs a month column, not a `DATE_TRUNC` at query time |

Each has to land as a physical column or row that the transform writes. The
step that decides *which* models must exist is this one, and nothing else in
the pipeline does it: inference reads the source you hand it, and code
generation places the models you name. If you skip planning, you generate a
faithful model of the raw rows that cannot answer the question that was asked.

## Backward-chain from the questions

Work **right to left** — from what the user wants to know, back to what must be
materialized. For each question:

1. **Name the answer's shape.** One number? A number per group? A ranking?
   Write it as a measure over a dimension: "net burn by month".
2. **Name the measure's column.** The measure is `Agg(one column)` and nothing
   more. Ask which single physical column it sums or averages. If the honest
   answer contains "…where…", "…minus…", "…divided by…", or "…but only…", that
   column does not exist yet — a derived model must produce it.
3. **Name the dimension's column.** Same test. "By month" over a date column is
   a derived column, not a query-time truncation.
4. **Ask what the column needs.** A classification needs a ruling. A ruling
   needs a rule source. A rule source may not exist — see
   [reference data](#reference-data-rulings-that-exist-in-no-source-csv), and
   [rulings you must NOT propose](#rulings-you-must-not-propose) when the
   missing piece is a number rather than a judgement.
5. **Stop when you reach a real source column.** Every chain terminates at a
   source column, at reference data the user must confirm, or at a measurement
   you cannot supply — in which case that chain stops **BLOCKED**, and the rest
   of the plan proceeds without it.

Collect the models the chains demand, then de-duplicate: several questions
usually converge on the same one or two derived models.

## A worked chain

> **Question:** "What is my burn multiple?"

- burn multiple = net burn ÷ net new ARR — **a ratio, which no metric can
  express.** So it is not one metric; it is two metrics the agent divides when
  presenting, or a derived column at the reporting grain.
- **net burn** = cash out − cash in, per month → needs a signed `amount` column
  and a `month` column at monthly grain. The source has a transaction date, not
  a month → **derived column**.
- cash out excludes internal transfers → a transfer must be excluded from the
  measure. The layer has no filtered metric → the transform must either drop
  transfer rows from the derived model or land the classification as a
  dimension the query groups by.
- expenses must split **COGS vs opex** → needs a `category` column that no
  source row carries → **derived column** from a ruling.
- that ruling is a **merchant → category** mapping → exists in no source CSV →
  **reference data the user must confirm** (next section).
- merchants the mapping does not cover must not silently vanish or land in the
  wrong bucket → they get an explicit **`needs_review`** category, and the
  transform asserts every source row landed in exactly one bucket.

**Resulting model plan:**

| Model | Kind | Grain | Why |
|---|---|---|---|
| `transactions` | base | one source transaction | the pristine export |
| `merchant_categories` | base (reference) | one merchant | the user-confirmed ruling, landed as data |
| `classified_spend` | derived | transaction × category | adds `category` (incl. `needs_review`), `month`, signed `amount` |
| `spend_metrics` | view | — | `SUM(amount)` over the `category` / `month` dimensions |

Note what the plan makes possible: "which merchants are unclassified?" is now a
query, not a support ticket, because `needs_review` is a value in a dimension.

## Base or derived? the decision test

| The model's rows are… | Kind |
|---|---|
| exactly the supplied export's rows, 1:1 | **base** — `data/<name>/`, key from a source column |
| the same entities, with new columns (classification, FX normalization, month column) | **derived**, keeps the source key |
| the same entities minus some (dedupe, filter) | **derived**, keeps the source key |
| one input row expanded into N (amortize, unpivot) | **derived**, new composite key from the grain |
| many input rows collapsed into one (monthly regrain) | **derived**, new composite key from the grain |
| a judgement the user supplied, not the system | **base reference model** — see below |

A derived model needs a real reason to exist. If a question is answerable by a
metric over an existing column grouped by an existing column, do **not** derive
anything — add the view and stop.

## Reference data: rulings that exist in no source CSV

Merchant→category rules, account mappings, department rollups: these are
judgements, and they are not in the export. They are also the most tempting
thing to hardcode, because a dict literal in the transform "just works".

**Never do that.** A constant baked into generated transform code is an
unreviewable fabrication sitting inside a governed answer: the user cannot see
it, cannot query it, cannot correct it, and cannot tell your guess apart from
their own policy. A wrong rate silently changes every number downstream.

This section covers rulings you *may* propose when no user is available to
confirm. Not every missing ruling qualifies: an FX rate, a discount rate, a tax
rate is a **measurement**, and a measurement is never proposed — see
[Rulings you must NOT propose](#rulings-you-must-not-propose) for the
discriminator before you land anything as PROPOSED.

Handle a proposable ruling this way:

1. **Surface it as a gap, with your proposal.** State plainly that the ruling is
   not in the data, show the distinct values it must cover (every distinct
   merchant, every currency present), and propose a mapping if you have a
   defensible one.
2. **Get explicit confirmation.** The user confirms, edits, or supplies their
   own. Use `AskUserQuestion` when the choice set is small and closed.

   **When no user is available to confirm** — an autonomous or batch run —
   confirmation is not optional-away, it is *deferred*. Do not skip the ruling,
   do not hardcode it, and do not stall. Instead:

   - **Land the proposed mapping as its own model anyway**, exactly as step 3
     describes. A proposed ruling that is queryable data can be reviewed and
     corrected; one that never got landed cannot.
   - **Route every uncovered value to `needs_review`.** Never widen a proposed
     rule to swallow values it does not actually cover.
   - **Record each unconfirmed ruling in a `DECISIONS.md`** at the closure
     root: the ruling, the values it covers, the evidence you based it on, and
     what a reviewer should check. One entry per ruling.
   - **State in the handoff that the rulings are PROPOSED, NOT CONFIRMED**, and
     name `DECISIONS.md` as the place to review them. An answer built on a
     proposed ruling must never be narrated as if the user had agreed to it.
3. **Land it as its own model.** Write the confirmed mapping to
   `data/<name>/<name>.csv` and promise it as a base model like any other —
   `merchant_categories(merchant, category)`, `account_departments(account,
   department)`. It gets a validated key (the thing it maps from) exactly like
   any base model. A measurement the user *does* supply — `fx_rates(currency,
   month, rate)` they hand you — lands here too, by this same flow; what you
   must never do is author those numbers yourself.
4. **Join to it in the transform.** The derived model looks the ruling up from
   the landed rows. The transform reads a table; it does not embed a policy.
5. **Cover the misses explicitly.** Any source value the mapping does not cover
   gets an explicit bucket (`needs_review`, `unmapped`) — never a silent drop
   and never a default that quietly resembles a real category. Assert
   totality: every source row landed in exactly one bucket.

The payoff is that the ruling becomes queryable data. The user can ask what is
in `needs_review`, correct one row of the mapping, and rebuild — instead of
asking you to re-generate code they cannot read.

One narrow exception: a definition that is genuinely structural rather than a
business judgement — the number of months in a year, cents-per-dollar — is not
reference data. If a reasonable user could disagree with the value, it is a
ruling, and it gets landed.

## Rulings you must NOT propose

The section above has one hard boundary. **You may propose a CLASSIFICATION.
You may never propose a MEASUREMENT.**

| | Classification — *propose it* | Measurement — *refuse to propose it* |
|---|---|---|
| Example | merchant → category, account → department | FX rate, discount rate, tax rate |
| Value set | closed and **observed** — you can enumerate every value from the data | continuous — no set to enumerate, any number is admissible |
| Reviewability | each row is individually checkable: "Anthropic → COGS" is right or wrong on its face | a rate is a fact about the world outside the data; nothing in the export contradicts a wrong one |
| Blast radius of a wrong guess | bounded to that value's rows, and visible | multiplies through **every** downstream number, invisibly |
| Escape hatch | `needs_review` honestly carries what the proposal doesn't cover | there is no `needs_review` for a number — you either have it or you fabricate it |

The discriminator in one question: **could the user look at this value and tell
it was wrong?** For "Lufthansa → opex", yes. For "EUR → 1.08", no — 1.08 and
1.19 are equally plausible on their face, and both produce a confident total.
That asymmetry, not the data type, is what makes one proposable and the other
not.

### What refusal actually does

Refusal applies to the **one underivable ruling only**. Every other derivation
in the plan remains mandatory — you do not get to derive less elsewhere because
one input was missing.

1. **Do not fabricate the value.** Not in transform code, not as a PROPOSED
   model. "Proposed" is not a license to invent a number; it is a license to
   land a judgement the user can read back. There is no defensible proposal for
   an exchange rate the way there is for a category mapping.
2. **Leave that one derivation undone.** Everything else still derives. Here:
   keep amounts in their **source currency**, and keep `currency` as a dimension
   on the derived model so no aggregate can silently mix units. A per-currency
   answer is honest; a single blended number built on an invented rate is not.
3. **Surface it as BLOCKED in `DECISIONS.md`** — a status distinct from
   PROPOSED. Name exactly the datum needed (which currencies, over what date
   range, at what precision) and which questions are limited until it arrives.
4. **Make the limitation travel.** State in the handoff that every
   cross-currency answer is per-currency until rates are supplied — the caveat
   belongs with every number it touches, not filed once in a doc nobody reopens.
   Once the user supplies rates, they land as a normal base reference model via
   the flow above and the derivation completes.

A worked contrast on the same closure: the merchant→category ruling is
**PROPOSED** — landed as `merchant_categories`, uncovered merchants routed to
`needs_review`, recorded in `DECISIONS.md`, and the derived model carries a
`category` dimension. The FX ruling on that same closure is **BLOCKED** — no
`fx_rates` model, amounts stay in USD/GBP/EUR, `currency` is a dimension, and
`DECISIONS.md` names the missing rates as the reason "total opex" is reported
per currency rather than as one figure.

## Confirm the plan before authoring

Before writing `models.py`, state the plan back in two or three lines: the base
models, the derived models with their grain and key, any reference data you
need confirmed, and which question each derived model exists to answer. A
derived model no question motivates should not be built. A question no model
answers is the gap to raise now — not after a build.
