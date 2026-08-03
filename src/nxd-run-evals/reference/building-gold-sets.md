# Building a gold set from your metrics and BI tiles

## Contents

- [Why a gold set](#why-a-gold-set)
- [Every tile is a question/answer pair](#every-tile-is-a-questionanswer-pair)
- [Compute gold from the definition, not the pixel](#compute-gold-from-the-definition-not-the-pixel)
- [Numeric grading rules](#numeric-grading-rules)
- [Stratify and cluster](#stratify-and-cluster)
- [Freezing gold to a JSON oracle](#freezing-gold-to-a-json-oracle)
- [The `gold()` authoring API](#the-gold-authoring-api)

## Why a gold set

An `answer` case is scored by **deterministic execution-accuracy**: the agent's
returned rows are compared, order-independently, to a *frozen* oracle row-set.
The gold set is that oracle. It is the single most valuable and most easily
corrupted asset in the suite — a wrong gold row silently marks correct agents
wrong and vice versa. Everything below is about building gold you can trust.

The comparison itself is **not** re-implemented in this harness. `nxd_eval`
imports the cross-DP `evals/cross-dp-joins/harness/score.py` core
(`score_one`, `rows_equal_name_aware`, `_norm_rowset`, `load_gold`), so the eval
and the text-to-SQL PoC never drift on what "PASS" means. You author gold; the
shared core decides equality.

## Every tile is a question/answer pair

A BI dashboard is a pre-built gold set in disguise. Each **tile** is:

- a **question** — "Revenue by region, this quarter" → `"Break down revenue by
  region for the current quarter."`
- an **answer** — the rows the tile renders.

Harvest procedure:

1. Enumerate the tiles on the dashboards your consumers actually use.
2. For each tile, write the natural-language question a consumer would ask to get
   that tile. Keep it in the consumer's words, not the metric's internal name.
3. Note the tile's metric definition (the aggregation, the group-by, the
   filters). This — not the rendered chart — is where the gold answer comes from.
4. Classify the behaviour: is the honest response to *answer*, to *clarify*
   (ambiguous), or to *abstain* (infeasible / PII-only)? Most tiles are `answer`;
   deliberately author `clarify` / `abstain` cases too, or the suite only measures
   the happy path.

## Compute gold from the definition, not the pixel

**Never read the number off the chart.** A rendered tile can be rounded, cropped,
cached from stale data, or filtered by a dashboard-level control you didn't
notice. The metric *definition* is the contract; the pixel is a lossy view of it.

Compute each gold row from the metric's own definition against the same data the
DP serves:

- Take the tile's underlying aggregation and grouping (`sum(amount)`,
  `group by region`, `where quarter = current`).
- Evaluate it against the DP's backing data (or the fixture `seed.sql` for an
  offline suite).
- Record the resulting rows as gold.

If the DP is offline-testable, the fixture `seed.sql` *is* the ground truth —
compute gold from it directly and the oracle is exact by construction. For a live
DP, run the metric's definition once through a trusted path and freeze the rows.

## Numeric grading rules

The `_norm_rowset` normalization the scorer applies, and what it means for how you
write gold:

- **Order-independent.** Rows are compared as a set (or multiset); row order and
  column order do not matter. Don't sort gold to match the agent.
- **Name-blind for a single measure.** With one numeric measure column, the
  column *name* is not compared — only the value set. `{"n": 4}` matches
  `{"subject_count": 4}`. This tolerates the agent aliasing a column.
- **Name-aware for ≥2 measures.** With two or more numeric measure columns, the
  scorer is name-aware: it FAILs a row where `revenue` and `cost` are swapped even
  though the value multiset is identical. This is the `rows_equal_name_aware`
  guard — it exists because a column-name-blind match would pass a query that
  returns the right numbers under the wrong labels. **Consequence:** a
  two-measure gold row pins which number is which; author both measure names.
- **Numeric tolerance.** Floats compare within a small tolerance, so `1000` and
  `1000.0` and `999.9999999` match. Don't hand-round gold to fewer digits than
  the DP returns — let the tolerance absorb it.
- **DISTINCT rows.** The signature is over distinct rows. If multiplicity is
  meaningful for a case, set `equality_mode="multiset"` on that gold record.

Practical rule: **single-measure gold is forgiving; multi-measure gold is
strict.** When you want to catch a metric mix-up, put both measures in one gold
row rather than splitting into two single-measure cases.

## Stratify and cluster

140 tiles that are all "metric X by dimension Y" do not make a strong suite —
they measure one behaviour 140 times. Two disciplines fix this:

**Stratify across behaviours.** Deliberately spread cases across the axes that
actually break agents:

- happy-path single-grain answers (baseline),
- chasm / fan-out traps (two facts at different grains — a naive join
  double-counts),
- confusable metrics (`titer_sum` vs `titer_avg`) → `clarify`,
- infeasible / nonexistent metric / incompatible dimension / PII-only grouping →
  `abstain`.

The canonical `evals/query-loop/test_suite.json` and the public
`evals/public/*/checks.json` are worked examples of this stratification — read
them before writing your own.

**Treat templates as clusters.** Questions that share a template (same metric,
different dimension value; or the same question asked over `epochs` repeats) are
*correlated*. They do not each contribute one independent data point. The stats
layer discounts them via a design effect and reports **N_eff** (see
`statistics.md`). For sizing: to *earn* a ±5% claim you need ~140 **distinct,
stratified** questions, not 140 rows from 28 templates.

## Freezing gold to a JSON oracle

You can pin gold rows inline in the suite (`gold.rows(...)`) or keep them in a
freeze file so the same oracle is shared with the PoC. The freeze file shape is
`{gold_id: {"rows": [...], ...}}` — the exact format the cross-DP `load_gold`
reads. Point `gold(records, frozen_path="frozen.json")` at it and each record's
`rows` are filled from the freeze, so a record can declare its *intent*
(`gold.query(measures=[...], group_by=[...])`) before its rows are frozen from a
trusted run.

## The `gold()` authoring API

```python
from nxd_eval import gold

# Pin explicit rows inline (set equality by default):
gold.rows("g_total", [{"order_count": 1287}])

# Multiset when row multiplicity matters:
gold.rows("g_events", [{"kind": "x"}, {"kind": "x"}], equality_mode="multiset")

# Declare intent now, fill rows from a freeze file later:
gold.query("g_by_region", measures=["order_count", "revenue"], group_by=["region"])

# Assemble the {gold_id: record} map a Suite carries; optionally inject frozen rows:
GOLD = gold(
    {
        "g_total": gold.rows("g_total", [{"order_count": 1287}]),
        "g_by_region": gold.query("g_by_region",
                                  measures=["order_count", "revenue"],
                                  group_by=["region"]),
    },
    frozen_path="frozen.json",   # fills g_by_region.rows from the freeze
)
```

Each record carries `question_id`, `rows`, `measures`, `group_by`, and
`equality_mode`. A `Case` links to a record by `gold_id`; the scorer looks the
record up in the suite's `gold` map and compares the agent's rows to
`record["rows"]` under `record["equality_mode"]`.
