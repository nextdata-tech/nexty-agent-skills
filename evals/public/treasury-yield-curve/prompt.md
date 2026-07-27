# Scenario: Treasury par yield curve

The workspace contains a vendored US Treasury snapshot under `data/`:

- `data/yield_curve/treasury-2020.csv` … `treasury-2024.csv` — Daily Treasury
  Par Yield Curve Rates, one file per calendar year, five years in total.
- `data/maturities/maturities.csv` — a small reference table describing the
  maturities that appear in those files.

Every file is exactly as it came out of the upstream export. Do not edit,
re-save, re-shape, or re-order them.

## What the author wants to know

1. What did the curve look like on a given day — the yield at each maturity,
   read from the short end to the long end?
2. How wide is the spread between the long end and the short end, day by day,
   and on which days was the curve **inverted**?
3. How has an individual maturity's yield moved over the five years, month by
   month?
4. Which maturities are bills, which are notes, and which are bonds?

## Task for the agent

Build a Pocket data product that answers those questions.

This is an NXD Pocket data product: local DuckDB through the `duckdb` output
port, loaded with dlt. You have the installed Nexty skills available — consult
them for the closure contract, the derivation rules, and the assert
requirements rather than inferring them from other examples on this machine.

Read the sources before you author anything — all five yield files, not just
the first one. The decisions this scenario turns on are visible in the values
and in the physical layout, not in the column names.

Work autonomously. No user is available to confirm a ruling, which does not
make confirmation optional — consult the skills for what to do with a ruling
you cannot get confirmed.

## How this is graded

The eval grades the landed data product, not your narration of it: whether the
four questions above are answerable from the semantic layer, whether the
numbers a consumer gets back are trustworthy, and whether anything you had to
decide is visible to the next reader.

Read the sources. The traps in this scenario are in the bytes.
