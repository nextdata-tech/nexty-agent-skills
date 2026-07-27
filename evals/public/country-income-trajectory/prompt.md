# Scenario: World Bank GDP by income group

The workspace contains a vendored World Bank snapshot under `data/`:

- `data/gdp/gdp.csv` — GDP in current US$ from the World Development
  Indicators, one row per country.
- `data/countries/countries.csv` — the country metadata file that ships
  alongside it.
- `data/PROVENANCE.md` — where the snapshot came from and what it is licensed
  under.

Both files are exactly as they came out of the upstream export. Do not edit,
re-save, or re-shape them.

## What the author wants to know

1. How has total GDP moved over time for each income group — high income,
   upper middle, lower middle, low?
2. Within a given year, how does one income group's total compare to another's?
3. Which countries sit in each income group?

## Task for the agent

Build a Pocket data product that answers those questions.

This is an NXD Pocket data product: local DuckDB through the `duckdb` output
port, loaded with dlt. You have the installed Nexty skills available — consult
them for the closure contract, the derivation rules, and the assert
requirements rather than inferring them from other examples on this machine.

Read the sources before you author anything. The decisions this scenario turns
on are visible in the values and in the file's physical layout, not in the
column names.

Work autonomously. No user is available to confirm a ruling, which does not
make confirmation optional — consult the skills for what to do with a ruling
you cannot get confirmed.

## How this is graded

The eval grades the landed data product, not your narration of it: whether the
questions above are answerable from the semantic layer, whether the numbers a
consumer gets back mean what a consumer would assume they mean, and whether
anything you had to decide is visible to the next reader.

Read the sources. The traps in this scenario are in the bytes.
