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

4. **Maturity ordering.** Labels are `1 Mo` … `30 Yr`. Lexical sorting puts
   `10 Yr` before `2 Yr`. A correct model derives a numeric sort key
   (e.g. maturity in months) rather than ordering on the label.
