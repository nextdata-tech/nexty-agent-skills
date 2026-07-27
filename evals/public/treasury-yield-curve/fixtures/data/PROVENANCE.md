# Daily Treasury Par Yield Curve Rates — vendored snapshot

## Source

US Department of the Treasury, Daily Treasury Par Yield Curve Rates.

<https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve>

Fetched per calendar year from the CSV export endpoint:

```
https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/<YEAR>/all?type=daily_treasury_yield_curve&field_tdr_date_value=<YEAR>&page&_format=csv
```

Snapshot taken 2026-07-27. Years 2020–2024, one file per year.
1,246 observation rows total (excluding headers), ~92 KB.

## Licence

US federal government work — public domain, no restriction on redistribution.
Vendoring a frozen snapshot into this repository is unambiguously permitted.

## Why vendored rather than fetched at run time

The eval harness pins a scenario checksum. Fetching at setup would let the
upstream file change under a scenario and turn a real regression into noise
(or hide one). The data is small and public-domain, so a frozen copy costs
little and buys exact reproducibility.

## Shape

Wide format: one row per business date, one column per maturity.

```
Date,"1 Mo","2 Mo","3 Mo","4 Mo","6 Mo","1 Yr","2 Yr","3 Yr","5 Yr","7 Yr","10 Yr","20 Yr","30 Yr"
12/31/2024,4.40,4.39,4.37,4.32,4.24,4.16,4.25,4.27,4.38,4.48,4.58,4.86,4.78
```

Note `Date` is `MM/DD/YYYY`.

## Properties this fixture is chosen to exercise

1. **Semi-additive measures.** A yield may be compared across maturities on one
   date and averaged over time, but must never be summed over time. A default
   `sum` aggregation on `yield` is wrong, and a monthly rollup should be
   end-of-period rather than a sum.

2. **Wide-to-long unpivot.** The 13 maturity columns must become a
   `(date, maturity, yield)` grain. Leaving them as 13 separate fields makes
   the cross-maturity spread a column formula the semantic layer cannot express.

3. **Null vs zero.** Maturities were introduced at different times. In the
   2020 file the `4 Mo` column is blank on all 251 rows (that maturity began
   later); `1 Mo`, `2 Mo` and `30 Yr` are fully populated. Coercing blank to
   `0` fabricates a 0% yield and silently corrupts every aggregate that
   touches it. Blank must land as null and be excluded from aggregation.

4. **Maturity ordering.** Labels are `1 Mo` … `30 Yr`. Lexical sorting yields
   `1 Mo, 1 Yr, 10 Yr, 2 Mo, 2 Yr, …` — a nonsense curve. A correct model
   orders on a numeric key, and that key is supplied as a second source
   (below) rather than hardcoded in transform code.

## Second source: `maturities/maturities.csv`

Hand-authored reference data, 13 rows — one per maturity label appearing in
the yield files. Verified to join 1:1 against the labels actually present:
13 labels, 13 rows, no unmatched label and no unused row.

| column | meaning |
|---|---|
| `maturity_label` | joins to the unpivoted yield grain (`1 Mo` … `30 Yr`) |
| `maturity_months` | numeric sort key — 1, 2, 3, 4, 6, 12, 24, 36, 60, 84, 120, 240, 360 |
| `tenor_bucket` | `bill` (≤ 12 mo), `note` (2–10 yr), `bond` (20–30 yr) |
| `first_published` | date Treasury began publishing that maturity |

### Why this is a separate source rather than transform code

The closure needs a label → months mapping to order the curve. The tempting
shortcut is a dict literal in `transform/main.py`. That is a rule violation:
reference data is landed, never hardcoded — a mapping baked into transform
code is invisible to the semantic layer and unreviewable.

Landing it as a source turns the temptation into the correct behaviour, and
makes this scenario exercise **two-source consumption and a join** rather than
a single-directory glob. The five yield files share one schema, so without
this second source the ingest half of the closure is trivial.

### What `first_published` explains

It is the documented reason for the blank cells, and the data agrees exactly:

- `4 Mo` — introduced 2022-10-19. Absent from all 251 rows of 2020 and all
  251 of 2021; present on only **50 of 249 rows in 2022**; complete in 2023
  and 2024.
- The other twelve maturities are complete across all five years.

The partial 2022 coverage is the sharper trap: a closure that coerces blank to
`0` corrupts part of one year while the rest looks correct, so the damage is
easy to miss in a spot check. Blank must land as null and be excluded from
aggregation — an average yield over a period spanning the introduction date
must not be dragged toward zero by rows where the maturity did not yet exist.
